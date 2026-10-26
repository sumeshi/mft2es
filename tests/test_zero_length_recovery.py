"""Native non-advancing attribute recovery, with subprocess time limits."""

import gc
import importlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import weakref

import pytest

from mft2es.models.Mft2es import Mft2es
from mft2es.models.MftRecordReader import MftRecordReader, native_records
from test_native_csv_contract import synthetic_file_record


def _unfix(record):
    record = bytearray(record)
    offset, count = struct.unpack_from("<HH", record, 4)
    replacements = record[offset + 2 : offset + count * 2]
    for sector in range(count - 1):
        end = (sector + 1) * 512
        record[end - 2 : end] = replacements[sector * 2 : sector * 2 + 2]
    return record


def _seal(record):
    offset, count = struct.unpack_from("<HH", record, 4)
    tails = [bytes(record[end - 2 : end]) for end in range(512, len(record) + 1, 512)]
    record[offset : offset + count * 2] = b"\x01\0" + b"".join(tails[: count - 1])
    for end in range(512, len(record) + 1, 512):
        record[end - 2 : end] = b"\x01\0"
    return bytes(record)


def _record(number, name, size=1024, attribute_offset=None):
    original = _unfix(synthetic_file_record(number, name))
    used = struct.unpack_from("<I", original, 24)[0]
    attributes = original[56:used]
    offset = attribute_offset or (56 if size == 1024 else 80)
    record = bytearray(size)
    record[:48] = original[:48]
    struct.pack_into("<HH", record, 4, 48, size // 512 + 1)
    struct.pack_into("<H", record, 20, offset)
    struct.pack_into("<II", record, 24, offset + len(attributes), size)
    record[offset : offset + len(attributes)] = attributes
    return _seal(record)


def _zero_length(record, second_attribute=False):
    record = _unfix(record)
    offset = struct.unpack_from("<H", record, 20)[0]
    if second_attribute:
        length = struct.unpack_from("<I", record, offset + 4)[0]
        attribute = record[offset : offset + length]
        offset += length
        record[offset : offset + length] = attribute
        struct.pack_into("<I", record, offset + length, 0xFFFFFFFF)
        struct.pack_into("<I", record, 24, offset + length + 4)
    struct.pack_into("<I", record, offset + 4, 0)
    return _seal(record)


_API_PROBE = """
import json,sys
from mft2es import mft2json, PartialExtractionError
try:
    records = mft2json(sys.argv[1], multiprocess=sys.argv[2] == 'True',
        chunk_size=int(sys.argv[4]), timeline_mode=sys.argv[3] == 'True')
except PartialExtractionError as error:
    print(json.dumps({'partial': True, 'records': error.records,
        'diagnostics': error.diagnostics}))
else:
    print(json.dumps({'partial': False, 'records': records, 'diagnostics': []}))
"""


def _probe(source, multiprocess=False, timeline=False, chunk_size=500):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _API_PROBE,
            str(source),
            str(multiprocess),
            str(timeline),
            str(chunk_size),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHON_CPU_COUNT": "2"},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _numbers(records, timeline=False):
    return [
        (
            r["windows"]["mft"]["record"]["number"]
            if timeline
            else r["header"]["record_number"]
        )
        for r in records
    ]


@pytest.mark.parametrize("size", [1024, 4096])
@pytest.mark.parametrize("multiprocess", [False, True])
@pytest.mark.parametrize("timeline", [False, True])
@pytest.mark.parametrize("chunk_size", [1, 500])
def test_native_zero_attribute_length_recovers_neighbors(
    tmp_path, size, multiprocess, timeline, chunk_size
):
    source = tmp_path / "zero-length-MFT"
    payload = (
        _record(0, "first.txt", size)
        + _zero_length(_record(1, "bad.txt", size))
        + _record(2, "last.txt", size)
    )
    source.write_bytes(payload)
    result = _probe(source, multiprocess, timeline, chunk_size)
    assert result["partial"] is True
    assert _numbers(result["records"], timeline) == (
        [0] * 4 + [2] * 4 if timeline else [0, 2]
    )
    assert len(result["diagnostics"]) == 1
    error = result["diagnostics"][0]
    assert error["record_index"] == 1
    assert error["stage"] == "parse"
    assert "MFT record 1 has zero attribute RecordLength" in error["error"]
    assert source.read_bytes() == payload


@pytest.mark.parametrize("bad_index", [0, 2])
@pytest.mark.parametrize("second_attribute", [False, True])
def test_native_zero_length_at_file_edges_and_later_attributes(
    tmp_path, bad_index, second_attribute
):
    source = tmp_path / "zero-edge-MFT"
    records = [_record(index, f"{index}.txt") for index in range(3)]
    records[bad_index] = _zero_length(records[bad_index], second_attribute)
    source.write_bytes(b"".join(records))
    result = _probe(source)
    assert _numbers(result["records"]) == [i for i in range(3) if i != bad_index]
    assert len(result["diagnostics"]) == 1
    assert result["diagnostics"][0]["record_index"] == bad_index


def test_native_parent_path_lookup_does_not_shift_stream_pairing(tmp_path):
    child = _unfix(_record(0, "child.txt"))
    offset = struct.unpack_from("<H", child, 20)[0]
    struct.pack_into("<Q", child, offset + 24, 1)
    source = tmp_path / "parent-zero-MFT"
    source.write_bytes(
        _seal(child) + _zero_length(_record(1, "parent")) + _record(2, "last.txt")
    )
    result = _probe(source, chunk_size=1)
    assert _numbers(result["records"]) == [0, 2]
    paths = [r["attributes"]["FileName"][-1]["data"]["path"] for r in result["records"]]
    assert "[Unknown]" in paths[0] and paths[0].endswith("child.txt")
    assert paths[1].endswith("last.txt")
    assert len(result["diagnostics"]) == 1


@pytest.mark.parametrize("zero", [False, True])
def test_native_fixups_are_applied_before_length_inspection(tmp_path, zero):
    source = tmp_path / "fixup-header-MFT"
    record = _record(0, "cross-sector.txt", attribute_offset=504)
    if zero:
        record = _zero_length(record)
    # The USA marker overwrites the high bytes of this RecordLength on disk.
    assert struct.unpack_from("<I", record, 508)[0] >= 65536
    source.write_bytes(record)
    result = _probe(source)
    assert result["partial"] is zero
    assert len(result["records"]) == (0 if zero else 1)
    assert len(result["diagnostics"]) == (1 if zero else 0)


@pytest.mark.parametrize("signature", [b"BAAD", bytes(4), b"NOPE"])
def test_native_non_file_and_unused_records_keep_native_behavior(tmp_path, signature):
    source = tmp_path / "signatures-MFT"
    middle = bytearray(_record(1, "middle.txt"))
    middle[:4] = signature
    source.write_bytes(_record(0, "first.txt") + middle + _record(2, "last.txt"))
    result = _probe(source)
    if signature == b"BAAD":
        assert _numbers(result["records"]) == [0, 1, 2]
        assert result["records"][1]["valid_fixup"] is None
    else:
        assert _numbers(result["records"]) == [0, 2]
    assert len(result["diagnostics"]) == (1 if signature == b"NOPE" else 0)


def test_native_fixup_mismatch_is_not_rejected(tmp_path):
    source = tmp_path / "mismatch-MFT"
    record = bytearray(_record(0, "mismatch.txt"))
    record[510:512] = b"\x02\0"
    source.write_bytes(record)
    result = _probe(source)
    assert result["partial"] is False
    assert result["records"][0]["valid_fixup"] is False


@pytest.mark.parametrize("zero", [False, True])
@pytest.mark.parametrize("timeline", [False, True])
def test_native_nonresident_sparse_attribute_preserves_or_recovers(
    tmp_path, zero, timeline
):
    record = _unfix(_record(0, "sparse.txt"))
    offset = struct.unpack_from("<H", record, 20)[0]
    offset += struct.unpack_from("<I", record, offset + 4)[0]
    attribute = (
        struct.pack("<IIBBHHH", 0x80, 0 if zero else 72, 1, 0, 0, 0x8000, 2)
        + struct.pack("<QQHHIQQQ", 0, 7, 64, 0, 0, 0, 32768, 0)
        + b"\x01\x08\0\0\0\0\0\0"
    )
    record[offset : offset + 72] = attribute
    struct.pack_into("<I", record, offset + 72, 0xFFFFFFFF)
    struct.pack_into("<I", record, 24, offset + 76)
    source = tmp_path / "nonresident-MFT"
    source.write_bytes(_seal(record) + _record(1, "last.txt"))
    result = _probe(source, timeline=timeline)
    assert result["partial"] is zero
    assert _numbers(result["records"], timeline) == (
        ([1] * 4 if zero else [0] * 4 + [1] * 4)
        if timeline
        else ([1] if zero else [0, 1])
    )
    if not zero and not timeline:
        assert "Sparse" in json.dumps(result["records"][0]["attributes"]["DATA"])


def test_native_sparse_hole_is_skipped_without_diagnostic(tmp_path):
    source = tmp_path / "sparse-hole-MFT"
    with source.open("wb") as stream:
        stream.write(_record(0, "first.txt"))
        stream.seek(2048)
        stream.write(_record(2, "last.txt"))
    result = _probe(source)
    assert result["partial"] is False
    assert _numbers(result["records"]) == [0, 2]


def test_native_baad_zero_length_is_recovered_without_fixup(tmp_path):
    source = tmp_path / "baad-zero-MFT"
    record = bytearray(_zero_length(_record(1, "bad.txt")))
    record[:4] = b"BAAD"
    source.write_bytes(_record(0, "first.txt") + record + _record(2, "last.txt"))
    result = _probe(source)
    assert _numbers(result["records"]) == [0, 2]
    assert len(result["diagnostics"]) == 1


def test_reader_delegates_short_reads_and_rewinds_rejections():
    good = _record(0, "first.txt")
    bad = _zero_length(_record(1, "bad.txt"))
    reader = MftRecordReader(io.BytesIO(good + bad + b"tail"))
    assert reader.read(1024) == good
    with pytest.raises(OSError, match="zero attribute RecordLength"):
        reader.read(1024)
    assert reader.tell() == 1024
    reader.seek(2048)
    assert reader.read(1024) == b"tail"
    assert reader.read(1024) == b""


def test_reader_preserves_read_only_stream_name(tmp_path):
    source = tmp_path / "named-MFT"
    source.write_bytes(_record(0, "first.txt"))
    with source.open("rb") as stream:
        reader = MftRecordReader(stream)
        assert reader.name == stream.name == str(source)
        with pytest.raises(AttributeError):
            reader.name = "other-MFT"


def test_native_callback_errors_drop_tracebacks_before_worker_transfer():
    reader = MftRecordReader(io.BytesIO(_zero_length(_record(0, "bad.txt"))))
    from mft import PyMftParser

    parser = PyMftParser(reader)
    errors = list(native_records(parser.entries_json()))
    assert len(errors) == 1 and isinstance(errors[0], OSError)
    assert errors[0].__traceback__ is None
    assert errors[0].__context__ is None
    assert errors[0].__cause__ is None


def test_zero_length_recovery_releases_owner_thread_parsers(tmp_path):
    source = tmp_path / "zero-gc-MFT"
    source.write_bytes(_record(0, "first.txt") + _zero_length(_record(1, "bad.txt")))
    was_enabled = gc.isenabled()
    gc.collect()
    gc.disable()
    try:
        model = Mft2es(source)
        reference = weakref.ref(model)
        try:
            assert _numbers(
                [
                    r
                    for batch in model.gen_timeline_records(False, 500, False)
                    for r in batch
                ]
            ) == [0]
            assert len(model.diagnostics) == 1
        finally:
            model.close()
        del model
        assert reference() is None
        collector = threading.Thread(target=gc.collect)
        collector.start()
        collector.join()
    finally:
        gc.collect()
        if was_enabled:
            gc.enable()


def test_constructor_second_open_failure_closes_first_handle(tmp_path, monkeypatch):
    source = tmp_path / "open-error-MFT"
    source.write_bytes(_record(0, "first.txt"))
    original_open = Path.open
    opened = []

    def fail_second(path, *args, **kwargs):
        if opened:
            raise OSError("second open failed")
        stream = original_open(path, *args, **kwargs)
        opened.append(stream)
        return stream

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_second)
        with pytest.raises(OSError, match="second open"):
            Mft2es(source)
    assert len(opened) == 1 and opened[0].closed


def test_constructor_failure_releases_parser_with_traceback_retained(
    tmp_path, monkeypatch
):
    source = tmp_path / "constructor-error-MFT"
    source.write_bytes(_record(0, "first.txt"))
    module = importlib.import_module("mft2es.models.Mft2es")
    references = []
    destroyed_threads = []

    class FirstParser:
        def __init__(self, stream):
            self.stream = stream

        def __del__(self):
            destroyed_threads.append(threading.get_ident())

    def fail_second(stream):
        if references:
            raise RuntimeError("second parser failed")
        parser = FirstParser(stream)
        references.append(weakref.ref(parser))
        return parser

    monkeypatch.setattr(module, "PyMftParser", fail_second)
    was_enabled = gc.isenabled()
    gc.collect()
    gc.disable()
    try:
        with pytest.raises(RuntimeError, match="second parser") as retained:
            Mft2es(source)
        assert retained.value.__traceback__ is not None
        assert references[0]() is None
        assert destroyed_threads == [threading.get_ident()]
    finally:
        gc.collect()
        if was_enabled:
            gc.enable()


@pytest.mark.parametrize("timeline", [False, True])
@pytest.mark.parametrize("multiprocess", [False, True])
@pytest.mark.parametrize("output_format", ["json", "jsonl"])
def test_native_cli_zero_length_publishes_partial_output_and_fails(
    tmp_path, timeline, multiprocess, output_format
):
    source = tmp_path / "zero-cli-MFT"
    source.write_bytes(
        _record(0, "first.txt")
        + _zero_length(_record(1, "bad.txt"))
        + _record(2, "last.txt")
    )
    output = tmp_path / f"output.{output_format}"
    command = [
        str(Path(sys.executable).with_name("mft2json")),
        str(source),
        "--quiet",
        "--format",
        output_format,
        "-o",
        str(output),
        "--timeline" if timeline else "--no-timeline",
    ]
    if multiprocess:
        command.append("--multiprocess")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHON_CPU_COUNT": "2"},
    )
    assert result.returncode == 1
    assert "Partial extraction" in result.stderr
    records = (
        json.loads(output.read_bytes())
        if output_format == "json"
        else [json.loads(line) for line in output.read_bytes().splitlines()]
    )
    assert _numbers(records, timeline) == ([0] * 4 + [2] * 4 if timeline else [0, 2])
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))
