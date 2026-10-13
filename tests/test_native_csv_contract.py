"""Native CSV/JSON pairing using synthetic NTFS FILE records, never evidence."""

import csv
import io
import json
import struct

import pytest
from mft import PyMftParser

from mft2es.models.Mft2es import Mft2es, filename_from_csv_blob


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
