"""Keep Timeline output and container independence while preparing common fields."""

from copy import deepcopy
import importlib
import ntpath

import orjson
import pytest

model = importlib.import_module("mft2es.models.Mft2es")


def original_timeline_record(
    record, attribute, attr_type, macb_type, timestamp_field, filepath, tags
):
    """The output construction before common-field preparation was introduced."""
    attr_data = attribute.get("data", {})
    record_header = record.get("header", {})
    attr_header = attribute.get("header", {})
    result = {
        "@timestamp": attr_data.get(timestamp_field),
        "event": {
            "action": f"mft-{attr_type.lower()}-{macb_type.lower()}",
            "category": ["file"],
            "type": [model.MACB_EVENT_TYPE_MAPPING[macb_type]],
            "kind": "event",
            "provider": "mft",
            "module": "windows",
            "dataset": "windows.mft",
        },
        "windows": {
            "mft": {
                "record": {
                    "number": record_header.get("record_number", 0),
                    "name": ntpath.basename(filepath) if filepath else "",
                    "path": filepath,
                },
                "header": {
                    key: value
                    for key, value in record_header.items()
                    if key != "record_number"
                },
                "attribute": {
                    "type": attr_type,
                    "macb_type": macb_type,
                    "header": {
                        key: value
                        for key, value in attr_header.items()
                        if key != "type_code"
                    },
                    "data": {
                        key: value
                        for key, value in attr_data.items()
                        if key not in model.MACB_MAPPING.values()
                    },
                },
            }
        },
        "log": {"file": {"path": "MFT"}},
        "tags": model.build_tags(tags),
    }
    if "valid_fixup" in record:
        result["windows"]["mft"]["valid_fixup"] = record["valid_fixup"]
    return result


def sample_record():
    return {
        "header": {
            "sequence": 2,
            "record_number": 7,
            "base_reference": {"entry": 0, "sequence": 0},
        },
        "attributes": [
            {
                "header": {
                    "attribute_id": index,
                    "type_code": attr_type,
                    "residential_header": {"data_size": 42},
                },
                "data": {
                    "name": f"名前{index}",
                    "created": "2024-01-01T00:00:00Z",
                    "accessed": None,
                    "modified": "2024-01-01T00:00:00Z",
                    "mft_modified": "2024-01-02T00:00:00Z",
                    "flags": ["ARCHIVE"],
                    "size": 0,
                },
            }
            for index, attr_type in enumerate(
                ("StandardInformation", "FileName", "FileName")
            )
        ]
        + [
            {"header": {"type_code": "DATA"}, "data": {"bytes": [0, 1]}},
            {"header": {"type_code": "FileName"}},
            {"header": {"type_code": "StandardInformation"}, "data": {}},
        ],
    }


@pytest.mark.parametrize("fixup", ["absent", True, False, None])
@pytest.mark.parametrize("tags", [None, "mft, case01,case01", [" host01 ", "mft"]])
@pytest.mark.parametrize("filepath", ["", "C:\\調査\\a,b.txt"])
def test_preparation_preserves_documents_order_and_serialized_bytes(
    fixup, tags, filepath
):
    record = sample_record()
    if fixup != "absent":
        record["valid_fixup"] = fixup
    before = deepcopy(record)
    expected = []
    for attribute in record["attributes"]:
        attr_type = attribute["header"]["type_code"]
        if attr_type not in model.TIMELINE_ATTRIBUTES or "data" not in attribute:
            continue
        expected.extend(
            original_timeline_record(
                record, attribute, attr_type, macb, field, filepath, tags
            )
            for macb, field in model.MACB_MAPPING.items()
        )

    result = model.format_timeline_records(record, filepath, "MFT", tags)

    assert result == expected
    assert record == before
    assert len(result) == 16
    for option in (0, orjson.OPT_INDENT_2, orjson.OPT_SORT_KEYS):
        assert orjson.dumps(result, option=option) == orjson.dumps(
            expected, option=option
        )


@pytest.mark.parametrize("macb,timestamp_field", list(model.MACB_MAPPING.items()))
def test_single_record_helper_keeps_its_output_contract(macb, timestamp_field):
    record = sample_record()
    record["valid_fixup"] = False
    attribute = record["attributes"][1]
    expected = original_timeline_record(
        record, attribute, "FileName", macb, timestamp_field, "C:\\a.txt", "host01"
    )

    result = model.create_timeline_record(
        record, attribute, "FileName", macb, timestamp_field, "C:\\a.txt", "MFT",
        "host01",
    )

    assert orjson.dumps(result) == orjson.dumps(expected)


def test_attribute_helper_keeps_macb_order_and_missing_timestamps():
    record = {"header": {"record_number": 7}, "valid_fixup": None}
    attribute = {"header": {"type_code": "FileName"}, "data": {"name": "a"}}
    expected = [
        original_timeline_record(record, attribute, "FileName", macb, field, "a", None)
        for macb, field in model.MACB_MAPPING.items()
    ]

    result = model.create_macb_records_for_attribute(
        record, attribute, "FileName", "a", "MFT"
    )

    assert orjson.dumps(result) == orjson.dumps(expected)
    assert all(document["@timestamp"] is None for document in result)


@pytest.mark.parametrize("attribute", [{}, {"header": {"type_code": "FileName"}}])
def test_attribute_without_data_does_not_prepare_unused_fields(attribute):
    assert model.create_macb_records_for_attribute(
        {}, attribute, "FileName", object(), "MFT", [object()]
    ) == []


def test_each_event_retains_independent_output_containers():
    record = sample_record()
    before = deepcopy(record)
    documents = model.format_timeline_records(record, "C:\\a.txt", "MFT", "host01")
    other_documents = orjson.dumps(documents[1:])
    first = documents[0]
    metadata = first["windows"]["mft"]
    containers = [
        first["event"], first["event"]["category"], first["event"]["type"],
        metadata["record"], metadata["header"], metadata["attribute"],
        metadata["attribute"]["header"], metadata["attribute"]["data"],
        first["log"]["file"], first["tags"],
    ]
    for container in containers:
        if isinstance(container, dict):
            container["changed"] = True
        else:
            container.append("changed")
    metadata["changed"] = True
    first["windows"]["changed"] = True
    first["log"]["changed"] = True

    assert orjson.dumps(documents[1:]) == other_documents
    assert record == before


def test_common_record_fields_are_prepared_once(monkeypatch):
    basename = model.ntpath.basename
    build_tags = model.build_tags
    calls = {"basename": 0, "tags": 0}

    def counted_basename(path):
        calls["basename"] += 1
        return basename(path)

    def counted_tags(tags):
        calls["tags"] += 1
        return build_tags(tags)

    monkeypatch.setattr(model.ntpath, "basename", counted_basename)
    monkeypatch.setattr(model, "build_tags", counted_tags)

    documents = model.format_timeline_records(sample_record(), "C:\\a.txt", "MFT")

    assert len(documents) == 16
    assert calls == {"basename": 1, "tags": 1}
