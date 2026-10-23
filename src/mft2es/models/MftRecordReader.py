"""Guard native reads and retain errors hidden by native serialization."""

from dataclasses import dataclass
import io
import struct
import warnings

from mft import PyMftParser

# Attribute types recognized by mft-rs 0.7.0. Unknown headers remain native errors.
_ATTRIBUTE_TYPES = frozenset(range(0x10, 0xF0, 0x10)) | {0x100}


@dataclass(frozen=True)
class NativeRecord:
    """A serialized native result with diagnostics safe for worker transfer."""

    value: object
    diagnostics: tuple


class MftRecordReader:
    """Read the original bytes, checking only complete, aligned native reads."""

    def __init__(self, stream, *, inspect_attributes=False, detect_path_cycles=False):
        self._stream = stream
        self._inspect_attributes = inspect_attributes
        self._detect_path_cycles = detect_path_cycles
        self._seen_records = None
        self._path_preflight_done = False
        self.diagnostics = []
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

    def begin_record(self):
        """Reset before native next(), which may also read parent records."""
        self.diagnostics = []
        self._seen_records = set() if self._detect_path_cycles else None
        self._path_preflight_done = False

    def read(self, size=-1):
        position = self._stream.tell()
        data = self._stream.read(size)
        if (
            self._record_size
            and size == self._record_size
            and len(data) == self._record_size
            and position % self._record_size == 0
        ):
            record_number = position // self._record_size
            try:
                # CSV resolves one linear parent chain per next(). Re-reading
                # FILE/BAAD in that chain is a cycle. ZERO entries skipped by
                # the iterator can be read again as parents without recursion.
                if self._seen_records is not None and data[:4] in (b"FILE", b"BAAD"):
                    if record_number in self._seen_records:
                        self._raise_path_cycle(record_number)
                    self._seen_records.add(record_number)
                    if len(self._seen_records) >= 32 and not self._path_preflight_done:
                        self._path_preflight_done = True
                        cycle = self._find_parent_cycle(data, record_number)
                        if cycle is not None:
                            self._raise_path_cycle(cycle)
                self._check_record(data, record_number)
                if self._inspect_attributes and data[:4] in (b"FILE", b"BAAD"):
                    self.diagnostics.extend(self._attribute_errors(data))
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

    def _raise_path_cycle(self, record_number):
        message = f"MFT parent reference cycle at record {record_number}"
        self.diagnostics.append(("path", f"OSError: {message}"))
        raise OSError(message)

    def _find_parent_cycle(self, data, record_number):
        # Short paths keep the exact native read/cache behavior. Before native
        # recursion grows deep, walk the remaining references iteratively once
        # for this CSV result. No full-file index or unbounded cache is built.
        position = self._stream.tell()
        try:
            self._stream.seek(0, io.SEEK_END)
            entry_count = self._stream.tell() // self._record_size
            seen = self._seen_records.copy()
            seen.remove(record_number)
            while 0 <= record_number < entry_count:
                if record_number in seen:
                    return record_number
                seen.add(record_number)
                if len(data) != self._record_size or data[:4] not in (b"FILE", b"BAAD"):
                    return None
                try:
                    self._check_record(data, record_number)
                    entry = self._isolated_entry(data)
                except (OSError, RuntimeError):
                    # Native get_entry will handle an unreadable parent itself.
                    return None
                if isinstance(entry, Exception):
                    return None
                names = [
                    attribute.attribute_content
                    for attribute in entry.attributes()
                    if not isinstance(attribute, Exception)
                    and attribute.type_code == 0x30
                ]
                names = [name for name in names if name is not None]
                best_name = next(
                    (
                        name
                        for name in names
                        if name.namespace in ("Win32", "Win32AndDos")
                    ),
                    names[0] if names else None,
                )
                if best_name is not None:
                    parent = best_name.parent_entry_id
                    # The native resolver treats these as root/orphan termini.
                    if parent in (0, 5, record_number):
                        return None
                else:
                    parent = entry.base_entry_id
                    if parent == 0:
                        return None
                record_number = parent
                if record_number in seen:
                    return record_number
                if not 0 <= record_number < entry_count:
                    return None
                self._stream.seek(record_number * self._record_size)
                data = self._stream.read(self._record_size)
        finally:
            self._stream.seek(position)
        return None

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
            if (
                attribute_type == 0x20
                and offset + 24 <= len(fixed)
                and fixed[offset + 8] == 0
            ):
                # mft-rs reads resident content at the cursor left by its header
                # parser, including an optional name, rather than data_offset.
                content_size = struct.unpack_from("<I", fixed, offset + 16)[0]
                name_size = fixed[offset + 9]
                content_start = offset + 24
                if name_size:
                    name_offset = struct.unpack_from("<H", fixed, offset + 10)[0]
                    content_start = offset + name_offset + name_size * 2
                if content_start <= len(fixed):
                    content_end = content_start + content_size
                    if content_end > len(fixed):
                        raise OSError(
                            f"MFT record {record_number} has truncated AttributeList "
                            f"content at record offset {offset}"
                        )
                    entry = content_start
                    while entry + 26 <= content_end:
                        entry_length = struct.unpack_from("<H", fixed, entry + 4)[0]
                        if entry_length == 0:
                            raise OSError(
                                f"MFT record {record_number} has zero AttributeList "
                                f"entry RecordLength at record offset {entry}"
                            )
                        entry += entry_length
            offset += length

    @staticmethod
    def _isolated_entry(data):
        # The public object API exposes errors that entries_json() discards.
        # Give it just one record: parent references cannot recurse into other
        # records. Its stride is taken from this copy's header, so normalize it
        # when a later record's own size field is damaged. Source bytes and the
        # original JSON serialization stay unchanged.
        isolated = bytearray(data)
        struct.pack_into("<I", isolated, 28, len(isolated))
        with warnings.catch_warnings():
            # The original native stream emits this warning with the actual
            # physical entry ID. Avoid a duplicate naming the isolated entry 0.
            warnings.filterwarnings(
                "ignore",
                message=r"WARN  \[mft::entry\].*fixup bytes are not equal",
                category=UserWarning,
            )
            parser = PyMftParser(io.BytesIO(isolated))
            entries = parser.entries()
            entry = next(entries)
        return entry

    @staticmethod
    def _attribute_errors(data):
        entry = MftRecordReader._isolated_entry(data)
        if isinstance(entry, Exception):
            return []
        return [
            ("attributes", f"{type(attribute).__name__}: {attribute}")
            for attribute in entry.attributes()
            if isinstance(attribute, Exception)
        ]


def native_records(entries, reader=None):
    """Remove callback frames on the owning thread before worker submission."""
    entries = iter(entries)
    while True:
        if reader is not None:
            reader.begin_record()
        try:
            record = next(entries)
        except StopIteration:
            return
        if isinstance(record, Exception):
            # Python read callbacks can return native error elements retaining
            # their traceback. Those frames can keep thread-affine parsers alive
            # until another thread runs GC. Diagnostics only need type/message.
            record.__traceback__ = None
            record.__context__ = None
            record.__cause__ = None
        if reader is not None and reader.diagnostics:
            yield NativeRecord(record, tuple(reader.diagnostics))
        else:
            yield record
