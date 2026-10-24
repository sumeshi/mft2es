"""Generated NTFS FILE records read by the native MFT parser."""

from pathlib import Path
import struct

PACKAGE = "mft2es"
JSON_COMMAND = "mft2json"
TIMELINE_MODES = (False, True)
SUPPORTS_MULTIPROCESSING = True
API_KWARGS = {}
CLI_ARGS = ()


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


def create_artifact(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "MFT"
    destination.write_bytes(
        synthetic_file_record(0, "first.txt")
        + synthetic_file_record(1, "second-日本語.txt")
    )
    return destination
