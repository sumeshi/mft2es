"""Keep native diagnostics while avoiding warning-filter changes on healthy reads."""

import importlib
import struct
import warnings

import orjson
import pytest
from mft import PyMftParser

from mft2es.models.MftRecordReader import MftRecordReader, native_records
from test_zero_length_recovery import _record


def _read_json(source):
    with source.open("rb") as stream:
        reader = MftRecordReader(stream, inspect_attributes=True)
        parser = PyMftParser(reader)
        records = list(native_records(parser.entries_json(), reader))
    assert all(isinstance(record, str) for record in records)
    return [orjson.loads(record) for record in records]


@pytest.mark.parametrize("signature", [b"FILE", b"BAAD"])
def test_healthy_inspection_does_not_change_warning_filters(
    tmp_path, monkeypatch, signature
):
    data = bytearray(_record(0, "healthy.txt"))
    data[:4] = signature
    source = tmp_path / "healthy-MFT"
    source.write_bytes(data)
    module = importlib.import_module("mft2es.models.MftRecordReader")

    def unexpected_filter_change(*args, **kwargs):
        raise AssertionError("healthy inspection must not change warning filters")

    with monkeypatch.context() as patch:
        patch.setattr(module.warnings, "catch_warnings", unexpected_filter_change)
        patch.setattr(module.warnings, "filterwarnings", unexpected_filter_change)
        records = _read_json(source)

    assert len(records) == 1
    assert records[0]["valid_fixup"] is (True if signature == b"FILE" else None)
    assert records[0]["attributes"]
    assert source.read_bytes() == data


@pytest.mark.parametrize("bad_field", ["offset", "count", "truncated"])
def test_unknown_fixups_keep_warning_suppression_fallback(bad_field):
    data = bytearray(_record(0, "unknown.txt"))
    if bad_field == "offset":
        struct.pack_into("<H", data, 4, len(data))
    elif bad_field == "count":
        struct.pack_into("<H", data, 6, 0)
    else:
        struct.pack_into("<H", data, 6, 4)

    assert MftRecordReader._check_record(data, 0) is True


def test_fixup_mismatch_keeps_warning_suppression_fallback():
    data = bytearray(_record(0, "mismatch.txt"))
    data[510:512] = b"\x02\0"

    assert MftRecordReader._check_record(data, 0) is True


def test_usa_marker_changed_by_isolation_remains_suppressed(tmp_path):
    # Later headers may disagree with the stride from the first record. The
    # inspector normalizes that field, which can itself change an unusual USA.
    middle = bytearray(_record(1, "overlap.txt"))
    struct.pack_into("<H", middle, 4, 28)
    struct.pack_into("<I", middle, 28, 2048)
    marker = middle[28:30]
    middle[510:512] = marker
    middle[1022:1024] = marker
    assert MftRecordReader._check_record(middle, 1) is True
    source = tmp_path / "overlapping-USA-MFT"
    payload = _record(0, "first.txt") + middle + _record(2, "last.txt")
    source.write_bytes(payload)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        records = _read_json(source)

    assert [record["header"]["record_number"] for record in records] == [0, 1, 2]
    assert all(record["valid_fixup"] is True for record in records)
    assert not [
        warning
        for warning in caught
        if "fixup bytes are not equal" in str(warning.message)
    ]
    assert source.read_bytes() == payload
