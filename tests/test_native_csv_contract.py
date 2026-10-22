"""Native CSV/JSON pairing using synthetic NTFS FILE records, never evidence."""

import csv
import gc
import io
import json
import struct
import subprocess
import sys
import threading
import weakref
from pathlib import Path

import pytest
from mft import PyMftParser

from mft2es.models.Mft2es import Mft2es, filename_from_csv_blob
from mft2es import PartialExtractionError, mft2json


def synthetic_file_record(header_number, name=None):
    """Build one fixed-up 1024-byte record with an optional resident FileName."""
    record = bytearray(1024)
    record[:4] = b"FILE"
    attributes = b""
    if name is not None:
        encoded = name.encode("utf-16le")
        timestamp = 132223104000000000
        payload = (
            struct.pack(
                "<QQQQQQQIIBB",
                5,
                timestamp,
                timestamp,
                timestamp,
                timestamp,
                0,
                0,
                0,
                0,
                len(encoded) // 2,
                1,
            )
            + encoded
        )
        attribute_size = (24 + len(payload) + 7) // 8 * 8
        attributes = (
            struct.pack(
                "<IIBBHHHIHBB",
                0x30,
                attribute_size,
                0,
                0,
                0,
                0,
                1,
                len(payload),
                24,
                1,
                0,
            )
            + payload
        )
        attributes = attributes.ljust(attribute_size, b"\0")
    struct.pack_into(
        "<HHQHHHHIIQHHI",
        record,
        4,
        48,
        3,
        0,
        1,
        1,
        56,
        1,
        60 + len(attributes),
        1024,
        0,
        0,
        0,
        header_number,
    )
    struct.pack_into("<HHH", record, 48, 1, 0, 0)
    attribute_end = 56 + len(attributes)
    record[56:attribute_end] = attributes
    struct.pack_into("<I", record, attribute_end, 0xFFFFFFFF)
    record[510:512] = record[1022:1024] = b"\x01\x00"
    return bytes(record)


@pytest.mark.parametrize("names", [None, ['comma, "日本語"\nnext.txt  ', "second.txt"]])
def test_native_csv_uses_signature_then_entry_id_and_full_path(names):
    payload = b"".join(
        synthetic_file_record(number, names[index] if names else None)
        for index, number in enumerate((123, 456))
    )
    json_parser = PyMftParser(io.BytesIO(payload))
    csv_parser = PyMftParser(io.BytesIO(payload))
    records = [json.loads(record) for record in json_parser.entries_json()]
    blobs = list(csv_parser.entries_csv())
    assert len(records) == len(blobs) == 2
    rows = [
        list(csv.reader(io.StringIO(blob.decode("utf-8"), newline="")))
        for blob in blobs
    ]
    assert rows[0][0][0:2] == ["Signature", "EntryId"]
    assert rows[0][0][-1] == "FullPath"
    for index, (record, blob, blob_rows) in enumerate(zip(records, blobs, rows)):
        row = blob_rows[-1]
        assert row[0] == "FILE"
        # Native JSON and CSV use the physical entry index, not header bytes 44–47.
        assert record["header"]["record_number"] == index
        assert row[1] == str(index)
        assert filename_from_csv_blob(blob, index) == row[-1]
        if names:
            assert row[-1].endswith(names[index])
        else:
            assert row[-1] == ""


@pytest.mark.parametrize("timeline", [False, True])
@pytest.mark.parametrize("multiprocess", [False, True])
def test_native_pairing_survives_one_record_chunks(
    tmp_path, monkeypatch, timeline, multiprocess
):
    names = ['comma, "日本語"\nnext.txt  ', "second.txt"]
    source = tmp_path / "synthetic-MFT"
    source.write_bytes(
        b"".join(
            synthetic_file_record(number, name)
            for number, name in zip((123, 456), names)
        )
    )
    with source.open("rb") as stream:
        csv_parser = PyMftParser(stream)
        expected_paths = [
            list(csv.reader(io.StringIO(blob.decode("utf-8"), newline="")))[-1][-1]
            for blob in csv_parser.entries_csv()
        ]
    parser = Mft2es(source)
    monkeypatch.setattr(parser, "get_cpu_count", lambda: 2)
    try:
        chunks = list(
            parser.gen_timeline_records(multiprocess, 1, timeline_mode=timeline)
        )
    finally:
        parser.close()
    records = [record for chunk in chunks for record in chunk]
    assert len(chunks) == 2
    if timeline:
        assert len(records) == 8
        assert [record["windows"]["mft"]["record"]["number"] for record in records] == [
            0
        ] * 4 + [1] * 4
        assert [record["windows"]["mft"]["record"]["path"] for record in records] == [
            expected_paths[0]
        ] * 4 + [expected_paths[1]] * 4
    else:
        assert len(records) == 2
        assert [record["header"]["record_number"] for record in records] == [0, 1]
        assert [
            record["attributes"]["FileName"]["data"]["path"] for record in records
        ] == expected_paths
    assert all(path.endswith(name) for path, name in zip(expected_paths, names))


@pytest.fixture
def damaged_mft(tmp_path):
    damaged = bytearray(synthetic_file_record(1, "damaged.txt"))
    damaged[:4] = b"NOPE"
    source = tmp_path / "damaged-MFT"
    source.write_bytes(
        synthetic_file_record(0, "first.txt")
        + damaged
        + synthetic_file_record(2, "last.txt")
    )
    return source


@pytest.mark.parametrize("timeline", [False, True])
@pytest.mark.parametrize("multiprocess", [False, True])
@pytest.mark.parametrize("chunk_size", [1, 500])
def test_native_error_elements_recover_both_neighbors(
    damaged_mft, monkeypatch, timeline, multiprocess, chunk_size
):
    parser = Mft2es(damaged_mft)
    monkeypatch.setattr(parser, "get_cpu_count", lambda: 2)
    try:
        records = [
            r
            for batch in parser.gen_timeline_records(
                multiprocess, chunk_size, timeline_mode=timeline
            )
            for r in batch
        ]
    finally:
        parser.close()
    if timeline:
        assert [r["windows"]["mft"]["record"]["number"] for r in records] == [0] * 4 + [
            2
        ] * 4
        paths = [r["windows"]["mft"]["record"]["path"] for r in records]
        assert all(p.endswith("first.txt") for p in paths[:4])
        assert all(p.endswith("last.txt") for p in paths[4:])
    else:
        assert [r["header"]["record_number"] for r in records] == [0, 2]
        assert records[0]["attributes"]["FileName"]["data"]["path"].endswith(
            "first.txt"
        )
        assert records[1]["attributes"]["FileName"]["data"]["path"].endswith("last.txt")
    assert len(parser.diagnostics) == 1
    diagnostic = parser.diagnostics[0]
    assert diagnostic["source_file"] == str(damaged_mft)
    assert diagnostic["record_index"] == 1
    assert diagnostic["stage"] == "parse"
    assert "Bad signature" in diagnostic["error"]


def test_native_api_exposes_partial_documents(damaged_mft):
    with pytest.raises(PartialExtractionError) as raised:
        mft2json(str(damaged_mft))
    assert [r["header"]["record_number"] for r in raised.value.records] == [0, 2]
    assert len(raised.value.diagnostics) == 1


def test_native_recovery_releases_parsers_on_their_owner_thread(damaged_mft):
    # A returned native Exception must not gain a traceback that keeps the
    # generator and its thread-affine parsers alive until another thread's GC.
    gc_was_enabled = gc.isenabled()
    gc.collect()
    gc.disable()
    try:
        parser = Mft2es(damaged_mft)
        reference = weakref.ref(parser)
        try:
            batches = list(parser.gen_timeline_records(False, 500))
            assert [
                r["header"]["record_number"] for batch in batches for r in batch
            ] == [0, 2]
            assert len(parser.diagnostics) == 1
        finally:
            parser.close()
        del parser

        # Refcounting should release the wrapper and native parsers immediately
        # here on the creating thread, even while cyclic GC is disabled.
        assert reference() is None
        collector = threading.Thread(target=gc.collect)
        collector.start()
        collector.join()
    finally:
        # On an assertion failure, collect retained parsers safely on the owner
        # thread and restore the caller's GC setting.
        gc.collect()
        if gc_was_enabled:
            gc.enable()


@pytest.mark.parametrize("output_format", ["json", "jsonl"])
@pytest.mark.parametrize("quiet", [False, True])
def test_native_cli_commits_partial_output_and_exits_one(
    damaged_mft, output_format, quiet
):
    output = damaged_mft.with_suffix("." + output_format)
    command = [
        str(Path(sys.executable).with_name("mft2json")),
        str(damaged_mft),
        "--format",
        output_format,
        "-o",
        str(output),
    ]
    if quiet:
        command.append("--quiet")
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1, result.stderr
    assert "Partial extraction" in result.stderr
    records = (
        json.loads(output.read_bytes())
        if output_format == "json"
        else [json.loads(line) for line in output.read_bytes().splitlines()]
    )
    assert [r["header"]["record_number"] for r in records] == [0, 2]
    if quiet:
        assert result.stdout == ""
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))


@pytest.mark.parametrize("output_format", ["json", "jsonl"])
def test_native_no_recovered_documents_preserves_existing_output(
    damaged_mft, output_format
):
    # A valid header establishes the native record size, but has no timeline
    # attributes. The following bad record produces a recoverable diagnostic.
    damaged_mft.write_bytes(
        synthetic_file_record(0) + damaged_mft.read_bytes()[1024:2048]
    )
    output = damaged_mft.with_suffix("." + output_format)
    output.write_bytes(b"previous output")
    result = subprocess.run(
        [
            str(Path(sys.executable).with_name("mft2json")),
            str(damaged_mft),
            "--timeline",
            "--format",
            output_format,
            "-o",
            str(output),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "Partial extraction" in result.stderr
    assert output.read_bytes() == b"previous output"
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))
