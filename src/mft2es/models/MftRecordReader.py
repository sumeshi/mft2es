"""Reject non-advancing attribute headers before the native MFT parser."""

import io
import struct

# Attribute types recognized by mft-rs 0.7.0. Unknown headers remain native errors.
_ATTRIBUTE_TYPES = frozenset(range(0x10, 0xF0, 0x10)) | {0x100}


class MftRecordReader:
    """Read the original bytes, checking only complete, aligned native reads."""

    def __init__(self, stream):
        self._stream = stream
        position = stream.tell()
        try:
            stream.seek(0)
            header = stream.read(32)
        finally:
            stream.seek(position)
        # The native parser derives its stride from this same first header.
        self._record_size = (
            struct.unpack_from("<I", header, 28)[0] if len(header) == 32 else 0
        )

    @property
    def name(self):
        return self._stream.name

    def read(self, size=-1):
        position = self._stream.tell()
        data = self._stream.read(size)
        if (
            self._record_size
            and size == self._record_size
            and len(data) == self._record_size
            and position % self._record_size == 0
        ):
            try:
                self._check_record(data, position // self._record_size)
            except OSError:
                # Native get_entry advances its expected position only after a
                # successful read. Restore this position on rejection as well,
                # including when a CSV path lookup re-reads a damaged parent.
                self._stream.seek(position)
                raise
        return data

    def seek(self, offset, whence=io.SEEK_SET):
        return self._stream.seek(offset, whence)

    def tell(self):
        return self._stream.tell()

    @staticmethod
    def _check_record(data, record_number):
        if data[:4] not in (b"FILE", b"BAAD") or len(data) < 24:
            return
        fixed = data
        if data[:4] == b"FILE":
            usa_offset, usa_size = struct.unpack_from("<HH", data, 4)
            # Leave invalid/truncated fixup arrays to the native parser. For
            # valid arrays, mirror its replacements even when the check fails.
            if (
                usa_size < 1
                or usa_offset + usa_size * 2 > len(data)
                or (usa_size - 1) * 512 > len(data)
            ):
                return
            fixed = bytearray(data)
            replacements = data[usa_offset + 2 : usa_offset + usa_size * 2]
            for sector in range(usa_size - 1):
                end = (sector + 1) * 512
                fixed[end - 2 : end] = replacements[sector * 2 : sector * 2 + 2]

        offset = struct.unpack_from("<H", fixed, 20)[0]
        while offset + 8 <= len(fixed):
            attribute_type, length = struct.unpack_from("<II", fixed, offset)
            if attribute_type not in _ATTRIBUTE_TYPES:
                # This includes the normal 0xFFFFFFFF end marker.
                return
            if length == 0:
                raise OSError(
                    f"MFT record {record_number} has zero attribute RecordLength "
                    f"at record offset {offset}"
                )
            offset += length


def native_records(entries):
    """Remove callback frames on the owning thread before worker submission."""
    for record in entries:
        if isinstance(record, Exception):
            # Python read callbacks can return native error elements retaining
            # their traceback. Those frames can keep thread-affine parsers alive
            # until another thread runs GC. Diagnostics only need type/message.
            record.__traceback__ = None
            record.__context__ = None
            record.__cause__ = None
        yield record
