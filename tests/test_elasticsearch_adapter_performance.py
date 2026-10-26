"""Avoid source copies when MFT documents need no ES-specific changes."""

from copy import deepcopy
import importlib
from unittest.mock import Mock

import orjson
import pytest

module = importlib.import_module("mft2es.models.ElasticsearchAdapter")


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"attributes": {}},
        {"attributes": {"DATA": [], "FileName": []}},
        {"attributes": {"DATA": [{"data": None}]}},
        {"attributes": {"DATA": [{"data": {"data_runs": []}}]}},
        {
            "attributes": {
                "DATA": [{"data": None}, {"data": {"data_runs": []}}],
                "FileName": [
                    {"data": {"name": "long.txt"}},
                    {"data": {"name": "LONG~1.TXT"}},
                ],
            }
        },
        {
            "attributes": {
                "DATA": [
                    {
                        "header": {
                            "residential_header": {
                                "vnc_first": "0x0",
                                "vnc_last": "0xffffffffffffffff",
                            }
                        },
                        "data": {"data_runs": []},
                    }
                ]
            }
        },
        {
            "@timestamp": "2020-01-01T00:00:00Z",
            "windows": {
                "mft": {
                    "attribute": {
                        "header": {"residential_header": {"data_size": 72}},
                        "data": {"name": "日本語.txt"},
                    }
                }
            },
        },
    ],
)
def test_no_conversion_keeps_source_without_copying(monkeypatch, record):
    before = orjson.dumps(record)
    copier = Mock(side_effect=AssertionError("unnecessary document copy"))
    monkeypatch.setattr(module, "deepcopy", copier)

    assert module.ElasticsearchAdapter(None).prepare_source(record) is record
    assert orjson.dumps(record) == before
    copier.assert_not_called()


@pytest.mark.parametrize("value", ["", "resident\n日本語"])
def test_resident_data_still_gets_a_detached_source(monkeypatch, value):
    record = {"attributes": {"DATA": [{"data": value}]}, "tags": ["mft"]}
    before = deepcopy(record)
    copier = Mock(wraps=deepcopy)
    monkeypatch.setattr(module, "deepcopy", copier)

    source = module.ElasticsearchAdapter(None).prepare_source(record)

    copier.assert_called_once_with(record)
    assert source == {
        "attributes": {"DATA": [{"data": {"resident_data": value}}]},
        "tags": ["mft"],
    }
    source["tags"].append("changed")
    assert record == before


@pytest.mark.parametrize("timeline", [False, True])
@pytest.mark.parametrize(
    "value", [False, True, 0, -1, 2**64 - 1, "0xffffffffffffffff", None, 1.0]
)
def test_vcn_conversion_keeps_existing_types_and_values(timeline, value):
    attribute = {
        "header": {"residential_header": {"vnc_first": value, "vnc_last": value}},
        "data": {"name": "example.txt"},
    }
    record = (
        {"windows": {"mft": {"attribute": attribute}}}
        if timeline
        else {"attributes": {"IndexAllocation": [attribute]}}
    )
    before = deepcopy(record)
    expected = deepcopy(record)
    expected_attribute = (
        expected["windows"]["mft"]["attribute"]
        if timeline
        else expected["attributes"]["IndexAllocation"][0]
    )
    converted = isinstance(value, int)
    expected_value = hex(value) if converted else value
    expected_attribute["header"]["residential_header"] = {
        "vnc_first": expected_value,
        "vnc_last": expected_value,
    }

    source = module.ElasticsearchAdapter(None).prepare_source(record)

    assert orjson.dumps(source) == orjson.dumps(expected)
    assert record == before
    assert (source is record) is not converted
    if converted:
        actual_attribute = (
            source["windows"]["mft"]["attribute"]
            if timeline
            else source["attributes"]["IndexAllocation"][0]
        )
        actual_attribute["data"]["name"] = "changed"
        assert record == before


def test_resident_data_and_vcn_changes_share_one_copy(monkeypatch):
    record = {
        "attributes": {
            "DATA": [{"data": "4142"}],
            "IndexAllocation": [
                {
                    "header": {
                        "residential_header": {"vnc_first": 0, "vnc_last": 2**64 - 1}
                    }
                }
            ],
        }
    }
    before = deepcopy(record)
    copier = Mock(wraps=deepcopy)
    monkeypatch.setattr(module, "deepcopy", copier)

    source = module.ElasticsearchAdapter(None).prepare_source(record)

    copier.assert_called_once_with(record)
    assert source["attributes"]["DATA"][0]["data"] == {"resident_data": "4142"}
    assert source["attributes"]["IndexAllocation"][0]["header"][
        "residential_header"
    ] == {"vnc_first": "0x0", "vnc_last": "0xffffffffffffffff"}
    assert record == before


def test_windows_attribute_selection_keeps_existing_precedence():
    # The native modes are separate, but retain the adapter's behavior even for
    # a caller-supplied document containing both structures.
    record = {
        "attributes": {
            "DATA": [
                {
                    "data": {"data_runs": []},
                    "header": {"residential_header": {"vnc_first": 0}},
                }
            ]
        },
        "windows": {"mft": {"attribute": {"header": {}}}},
    }
    assert module.ElasticsearchAdapter(None).prepare_source(record) is record


@pytest.mark.parametrize("position", [0, 1, 2])
def test_resident_data_conversion_inspects_every_array_position(monkeypatch, position):
    attributes = [{"data": {"data_runs": []}} for _ in range(3)]
    attributes[position] = {"data": "4142"}
    record = {"attributes": {"DATA": attributes}}
    before = deepcopy(record)
    copier = Mock(wraps=deepcopy)
    monkeypatch.setattr(module, "deepcopy", copier)

    source = module.ElasticsearchAdapter(None).prepare_source(record)

    copier.assert_called_once_with(record)
    expected = deepcopy(before)
    expected["attributes"]["DATA"][position]["data"] = {"resident_data": "4142"}
    assert source == expected
    assert record == before


@pytest.mark.parametrize("type_code", ["DATA", "BITMAP", "IndexAllocation"])
@pytest.mark.parametrize("position", [0, 1, 2])
def test_vcn_conversion_inspects_every_type_and_array_position(type_code, position):
    attributes = [{"header": {}} for _ in range(3)]
    attributes[position]["header"]["residential_header"] = {
        "vnc_first": 0,
        "vnc_last": 2**64 - 1,
    }
    record = {"attributes": {type_code: attributes}}
    before = deepcopy(record)

    source = module.ElasticsearchAdapter(None).prepare_source(record)

    expected = deepcopy(before)
    expected["attributes"][type_code][position]["header"]["residential_header"] = {
        "vnc_first": "0x0",
        "vnc_last": "0xffffffffffffffff",
    }
    assert source == expected
    assert record == before


def test_adapter_does_not_access_mapping_or_index_management():
    class BulkOnlyClient:
        def __getattr__(self, name):
            raise AssertionError(f"Unexpected Elasticsearch client access: {name}")

    record = {"attributes": {"DATA": [{"data": "4142"}, {"data": ""}]}}
    records = [record]
    adapter = module.ElasticsearchAdapter(BulkOnlyClient())

    assert adapter.prepare_records(records, "operator-owned-index") is records
    assert adapter.prepare_source(record)["attributes"]["DATA"] == [
        {"data": {"resident_data": "4142"}},
        {"data": {"resident_data": ""}},
    ]
