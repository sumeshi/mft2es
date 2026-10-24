import importlib
import json

import pytest

from mft2es.models.Mft2es import (
    process_standard_by_chunk,
    process_timeline_by_chunk,
)


def encoded_record(number):
    return json.dumps(
        {
            "header": {"record_number": number},
            "attributes": [
                {
                    "header": {"type_code": "FileName"},
                    "data": {"modified": "2020-01-01T00:00:00Z"},
                }
            ],
        }
    )


def csv_row(number):
    return f"Signature,EntryId,FullPath\nFILE,{number},file-{number}.txt\n".encode()


@pytest.mark.parametrize("timeline", [False, True])
@pytest.mark.parametrize(
    "failure,stage",
    [
        ("native_json", "parse"),
        ("native_csv", "parse"),
        ("invalid_json", "json"),
        ("invalid_csv", "csv"),
        ("normalization", "normalize"),
    ],
)
def test_failed_pair_does_not_discard_neighbors_or_shift_filenames(
    timeline, failure, stage
):
    records = [encoded_record(i) for i in range(3)]
    rows = [csv_row(i) for i in range(3)]
    if failure == "native_json":
        records[1] = RuntimeError("bad FILE record")
    elif failure == "native_csv":
        rows[1] = RuntimeError("bad CSV record")
    elif failure == "invalid_json":
        records[1] = "not JSON"
    elif failure == "invalid_csv":
        rows[1] = csv_row(99)
    else:
        records[1] = json.dumps({"header": {"record_number": 1}, "attributes": [None]})

    diagnostics = []
    if timeline:
        output = process_timeline_by_chunk(
            records, rows, "MFT", ["case"], diagnostics, 100
        )
        assert [r["windows"]["mft"]["record"]["number"] for r in output] == [0] * 4 + [
            2
        ] * 4
        assert [r["windows"]["mft"]["record"]["path"] for r in output] == [
            "file-0.txt"
        ] * 4 + ["file-2.txt"] * 4
    else:
        output = process_standard_by_chunk(records, rows, ["case"], diagnostics, 100)
        assert [r["header"]["record_number"] for r in output] == [0, 2]
        assert [r["attributes"]["FileName"]["data"]["path"] for r in output] == [
            "file-0.txt",
            "file-2.txt",
        ]
    assert all(r["tags"] == ["mft", "case"] for r in output)
    assert len(diagnostics) == 1
    assert diagnostics[0]["record_index"] == 101
    assert diagnostics[0]["record_number"] == (
        None if failure in ("native_json", "invalid_json") else 1
    )
    assert diagnostics[0]["stage"] == stage
    assert diagnostics[0]["error"]


@pytest.mark.parametrize("stream", ["json", "csv"])
def test_native_exception_items_keep_their_original_traceback(stream):
    records = [encoded_record(i) for i in range(3)]
    rows = [csv_row(i) for i in range(3)]
    error = RuntimeError("bad native record")
    original_traceback = error.__traceback__
    if stream == "json":
        records[1] = error
    else:
        rows[1] = error
    diagnostics = []

    output = process_standard_by_chunk(records, rows, diagnostics=diagnostics)

    assert [r["header"]["record_number"] for r in output] == [0, 2]
    assert error.__traceback__ is original_traceback
    assert len(diagnostics) == 1
    assert diagnostics[0]["stage"] == "parse"
    assert diagnostics[0]["record_number"] == (None if stream == "json" else 1)


def test_native_csv_error_is_reported_even_if_json_cannot_supply_a_record_number():
    error = RuntimeError("bad native CSV record")
    diagnostics = []

    output = process_standard_by_chunk(["not JSON"], [error], diagnostics=diagnostics)

    assert output == []
    assert error.__traceback__ is None
    assert diagnostics == [
        {
            "record_index": 0,
            "record_number": None,
            "stage": "parse",
            "error": "RuntimeError: bad native CSV record",
        }
    ]


@pytest.mark.parametrize("timeline", [False, True])
def test_chunk_length_mismatch_remains_fatal(timeline):
    with pytest.raises(RuntimeError, match="lengths do not match"):
        if timeline:
            process_timeline_by_chunk([encoded_record(0)], [], "MFT")
        else:
            process_standard_by_chunk([encoded_record(0)], [])


@pytest.mark.parametrize("input_count", [1, 2])
def test_es_cli_continues_after_partial_extraction(
    tmp_path, monkeypatch, capsys, input_count
):
    module = importlib.import_module("mft2es.views.Mft2esView")
    paths = [tmp_path / name for name in ("first", "second")][:input_count]
    for path in paths:
        path.write_bytes(b"MFT")
    attempted = []

    class Presenter:
        def __init__(self, input_path, **kwargs):
            self.input_path = input_path

        def bulk_import(self):
            attempted.append(self.input_path)
            if self.input_path == paths[0]:
                raise module.PartialExtractionError([{"error": "bad record"}])

    monkeypatch.setattr(module, "Mft2esPresenter", Presenter)
    monkeypatch.setattr("sys.argv", ["mft2es", "--quiet", *(str(p) for p in paths)])
    with pytest.raises(SystemExit) as exited:
        module.Mft2esView().run()
    assert exited.value.code == 1
    assert attempted == paths
    captured = capsys.readouterr()
    assert "Partial extraction" in captured.err
    assert "no valid MFT files" not in captured.err
    assert captured.out == ""
