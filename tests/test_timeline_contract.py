import json
from pathlib import Path

import pytest

from mft2es.models.Mft2es import (
    MACB_EVENT_TYPE_MAPPING,
    build_tags,
    format_standard_record,
    format_timeline_records,
    parse_tags,
)


@pytest.mark.parametrize(
    ("macb_type", "event_type"),
    [("M", "modify"), ("A", "access"), ("C", "change"), ("B", "creation")],
)
@pytest.mark.parametrize("attribute_type", ["StandardInformation", "FileName"])
def test_timeline_macb_event_types_preserve_existing_fields(
    macb_type, event_type, attribute_type
):
    timestamp_field = {
        "M": "modified",
        "A": "accessed",
        "C": "mft_modified",
        "B": "created",
    }[macb_type]
    record = {
        "header": {"record_number": 7},
        "attributes": [
            {
                "header": {"type_code": attribute_type},
                "data": {timestamp_field: "2007-06-30T12:50:52.252395Z"},
            }
        ],
    }

    result = next(
        result
        for result in format_timeline_records(record, "C:/sample.txt", "MFT")
        if result["windows"]["mft"]["attribute"]["macb_type"] == macb_type
    )

    assert result["event"]["type"] == [event_type]
    assert result["event"]["action"] == (
        f"mft-{attribute_type.lower()}-{macb_type.lower()}"
    )
    assert result["event"]["category"] == ["file"]
    assert result["windows"]["mft"]["attribute"]["macb_type"] == macb_type


def test_timeline_macb_mapping_covers_all_four_types():
    assert MACB_EVENT_TYPE_MAPPING == {
        "M": "modify",
        "A": "access",
        "C": "change",
        "B": "creation",
    }


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (None, ["mft"]),
        ("mft, host01,host01,,case01 ", ["mft", "host01", "case01"]),
        ([" host01 ", "mft", "host01", "", "case01"], ["mft", "host01", "case01"]),
        (("host01", "case01", "host01"), ["mft", "host01", "case01"]),
    ],
)
def test_tags_normalize_and_deduplicate_in_stable_order(tags, expected):
    assert build_tags(tags) == expected


def test_standard_mode_keeps_record_shape_and_normalizes_tags():
    record = {"header": {}, "attributes": []}

    result = format_standard_record(record, "sample.txt", "mft,host01,mft")

    assert result == {"header": {}, "attributes": {}, "tags": ["mft", "host01"]}


def test_timeline_json_string_tags_use_common_parser():
    encoded_record = json.dumps(
        {
            "header": {"record_number": 7},
            "attributes": [
                {
                    "header": {"type_code": "StandardInformation"},
                    "data": {"modified": "2007-06-30T12:50:52.252395Z"},
                }
            ],
        }
    )
    csv_row = b"7,0,0,C:/sample.txt"

    from mft2es.models.Mft2es import process_timeline_by_chunk

    result = process_timeline_by_chunk(
        [encoded_record], [csv_row], "MFT", tags="mft, host01,host01"
    )

    assert result[0]["tags"] == ["mft", "host01"]
    assert parse_tags([" host01 ", "case01"]) == ["host01", "case01"]


@pytest.mark.parametrize("timeline", [False, True])
@pytest.mark.parametrize("input_kind", ["relative", "symlink"])
def test_json_and_es_preserve_the_same_absolute_evidence_path(
    tmp_path, monkeypatch, timeline, input_kind
):
    import importlib

    from mft2es.presenters.Mft2esPresenter import Mft2esPresenter
    from mft2es.presenters.Mft2jsonPresenter import Mft2jsonPresenter

    source = tmp_path / "MFT"
    source.write_bytes(b"fixture")
    monkeypatch.chdir(tmp_path)
    supplied = Path("MFT")
    if input_kind == "symlink":
        supplied = Path("alias")
        supplied.symlink_to(source)
    encoded = json.dumps(
        {
            "header": {"record_number": 7},
            "attributes": [
                {
                    "header": {"type_code": "StandardInformation"},
                    "data": {"modified": "2007-06-30T12:50:52.252395Z"},
                }
            ],
        }
    )

    class Parser:
        def __init__(self, stream):
            assert Path(stream.name) == source

        def entries_json(self):
            return iter([encoded])

        def entries_csv(self):
            return iter([b"7,0,0,C:/sample.txt"])

    module = importlib.import_module("mft2es.models.Mft2es")
    monkeypatch.setattr(module, "PyMftParser", Parser)
    output = tmp_path / "output.json"
    Mft2jsonPresenter(
        supplied, str(output), is_quiet=True, timeline_mode=timeline
    ).export_json()
    exported = json.loads(output.read_text())
    for path in (supplied, source):
        presenter = Mft2esPresenter(path, is_quiet=True, timeline_mode=timeline)
        records = [record for chunk in presenter.mft2es() for record in chunk]
        assert records == exported
        if timeline:
            assert all(
                record["log"]["file"]["path"] == str(source) for record in records
            )


def test_cli_comma_separated_tags_reach_existing_argument(tmp_path, monkeypatch):
    import importlib

    source = tmp_path / "$MFT"
    source.write_bytes(b"fixture")
    captured = {}
    module = importlib.import_module("mft2es.views.Mft2jsonView")

    class Presenter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def export_json(self):
            pass

    monkeypatch.setattr(module, "Mft2jsonPresenter", Presenter)
    monkeypatch.setattr("sys.argv", ["mft2json", str(source), "--tags", "mft,host01"])

    module.Mft2jsonView().run()

    assert captured["tags"] == "mft,host01"


@pytest.mark.parametrize("output_format", ["json", "jsonl"])
@pytest.mark.parametrize("timeline_mode", [False, True], ids=["standard", "timeline"])
def test_json_and_jsonl_keep_same_record_schema(
    tmp_path, monkeypatch, output_format, timeline_mode
):
    import importlib

    from mft2es.presenters.Mft2jsonPresenter import Mft2jsonPresenter

    if timeline_mode:
        record = format_timeline_records(
            {
                "header": {"record_number": 7},
                "attributes": [
                    {
                        "header": {"type_code": "StandardInformation"},
                        "data": {"modified": "2007-06-30T12:50:52.252395Z"},
                    }
                ],
            },
            "C:/sample.txt",
            "MFT",
            tags="host01",
        )[0]
    else:
        record = format_standard_record(
            {"header": {"record_number": 7}, "attributes": []},
            "C:/sample.txt",
            tags="host01",
        )

    class Parser:
        def __init__(self, _path):
            pass

        def gen_timeline_records(self, **_kwargs):
            assert _kwargs["timeline_mode"] is timeline_mode
            yield [record]

        def close(self):
            pass

    module = importlib.import_module(Mft2jsonPresenter.__module__)
    monkeypatch.setattr(module, "Mft2es", Parser)
    source = tmp_path / "input.mft"
    source.write_bytes(b"fixture")
    output = tmp_path / ("output.jsonl" if output_format == "jsonl" else "output.json")

    Mft2jsonPresenter(
        source,
        output,
        is_quiet=True,
        timeline_mode=timeline_mode,
        output_format=output_format,
    ).export_json()

    if output_format == "json":
        records = json.loads(output.read_text())
    else:
        records = [json.loads(line) for line in output.read_text().splitlines()]
    assert records == [record]


@pytest.mark.parametrize(
    "additional_tags",
    ["mft,host01", ["mft", "host01"], ("mft", "host01")],
    ids=["str", "list", "tuple"],
)
def test_public_mft2json_api_preserves_additional_tags_input(
    monkeypatch, additional_tags
):
    import mft2es

    class Parser:
        def __init__(self, _path):
            pass

        def gen_timeline_records(self, **kwargs):
            yield [
                format_standard_record(
                    {"attributes": []}, "sample.txt", tags=kwargs["tags"]
                )
            ]

        def close(self):
            pass

    monkeypatch.setattr(mft2es, "Mft2es", Parser)

    records = mft2es.mft2json("dummy", additional_tags=additional_tags)

    assert records[0]["tags"] == ["mft", "host01"]
