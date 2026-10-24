# coding: utf-8
import ntpath
import csv
import io
import logging
from pathlib import Path
from typing import Generator, Iterable, List, Optional, Sequence, Union
from itertools import islice, zip_longest

import orjson
from mft import PyMftParser

from .MultiprocessingUtils import SafeMultiprocessingMixin
from .MultiprocessingUtils import mp as mp
from .MultiprocessingUtils import ordered_pool_results
from .MftRecordReader import MftRecordReader, NativeRecord, native_records

# Constants for timeline analysis
MACB_MAPPING = {"M": "modified", "A": "accessed", "C": "mft_modified", "B": "created"}
MACB_EVENT_TYPE_MAPPING = {
    "M": "modify",
    "A": "access",
    "C": "change",
    "B": "creation",
}

# Target attributes for timeline analysis
TIMELINE_ATTRIBUTES = ["StandardInformation", "FileName"]
TagsInput = Optional[Union[str, Sequence[str]]]
logger = logging.getLogger(__name__)


class PartialExtractionError(RuntimeError):
    def __init__(self, diagnostics, records=None):
        self.diagnostics = list(diagnostics)
        self.records = records
        super().__init__(
            f"Partial extraction: {len(self.diagnostics)} failure(s); "
            "output is incomplete."
        )


def validate_chunk_size(chunk_size: int) -> None:
    if type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")


def filename_from_csv_blob(blob: bytes, record_number: int) -> str:
    header = None
    for row in csv.reader(io.StringIO(blob.decode("utf-8"), newline="")):
        if not row:
            continue
        if "EntryId" in row and "FullPath" in row:
            header = [field.strip() for field in row]
            continue
        entry_id_column = header.index("EntryId") if header else 1
        full_path_column = header.index("FullPath") if header else -1
        if len(row) > entry_id_column and row[entry_id_column].strip() == str(
            record_number
        ):
            return row[full_path_column]
    raise ValueError(f"CSV row for MFT record {record_number} was not found")


def parse_tags(tags: TagsInput) -> List[str]:
    if not tags:
        return []
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    if isinstance(tags, Sequence):
        return [t.strip() for t in tags if t and t.strip()]
    return []


def build_tags(tags: TagsInput = None) -> List[str]:
    """Return the builtin MFT tag followed by unique user tags."""
    return list(dict.fromkeys(["mft", *parse_tags(tags)]))


def generate_chunks(chunk_size: int, iterable: Iterable) -> Generator:
    validate_chunk_size(chunk_size)
    i = iter(iterable)
    piece = list(islice(i, chunk_size))
    while piece:
        yield piece
        piece = list(islice(i, chunk_size))


def create_timeline_record(
    record: dict,
    attribute: dict,
    attr_type: str,
    macb_type: str,
    timestamp_field: str,
    filepath: str,
    mft_file_path: str,
    tags: Optional[List[str]] = None,
) -> dict:
    attr_data = attribute.get("data", {})
    timestamp_fields = MACB_MAPPING.values()
    return _create_timeline_record(
        record,
        attr_type,
        macb_type,
        attr_data.get(timestamp_field),
        mft_file_path,
        _timeline_record_context(record, filepath, tags),
        {k: v for k, v in attribute.get("header", {}).items() if k != "type_code"},
        {k: v for k, v in attr_data.items() if k not in timestamp_fields},
        f"mft-{attr_type.lower()}-{macb_type.lower()}",
    )


def _timeline_record_context(record, filepath, tags):
    """Prepare record fields once without sharing output containers."""
    record_header = record.get("header", {})
    return (
        {
            "number": record_header.get("record_number", 0),
            "name": ntpath.basename(filepath) if filepath else "",
            "path": filepath,
        },
        {k: v for k, v in record_header.items() if k != "record_number"},
        build_tags(tags),
    )


def _create_timeline_record(
    record,
    attr_type,
    macb_type,
    timestamp,
    mft_file_path,
    context,
    attr_header,
    attr_data,
    action,
):
    record_fields, record_header, base_tags = context

    result = {
        "@timestamp": timestamp,
        "event": {
            "action": action,
            "category": ["file"],
            "type": [MACB_EVENT_TYPE_MAPPING[macb_type]],
            "kind": "event",
            "provider": "mft",
            "module": "windows",
            "dataset": "windows.mft",
        },
        "windows": {
            "mft": {
                "record": record_fields.copy(),
                "header": record_header.copy(),
                "attribute": {
                    "type": attr_type,
                    "macb_type": macb_type,
                    "header": attr_header.copy(),
                    "data": attr_data.copy(),
                },
            },
        },
        "log": {"file": {"path": mft_file_path}},
        "tags": base_tags.copy(),
    }
    if "valid_fixup" in record:
        result["windows"]["mft"]["valid_fixup"] = record["valid_fixup"]
    return result


def create_macb_records_for_attribute(
    record: dict,
    attribute: dict,
    attr_type: str,
    filepath: str,
    mft_file_path: str,
    tags: Optional[List[str]] = None,
) -> List[dict]:
    if not attribute or "data" not in attribute:
        return []
    return _macb_records_for_attribute(
        record,
        attribute,
        attr_type,
        mft_file_path,
        _timeline_record_context(record, filepath, tags),
    )


def _macb_records_for_attribute(record, attribute, attr_type, mft_file_path, context):
    attr_data = attribute["data"]
    attr_header = {
        k: v for k, v in attribute.get("header", {}).items() if k != "type_code"
    }
    timestamp_fields = MACB_MAPPING.values()
    data = {k: v for k, v in attr_data.items() if k not in timestamp_fields}
    action_prefix = f"mft-{attr_type.lower()}-"

    records = []
    for macb_type, timestamp_field in MACB_MAPPING.items():
        timeline_record = _create_timeline_record(
            record,
            attr_type,
            macb_type,
            attr_data.get(timestamp_field),
            mft_file_path,
            context,
            attr_header,
            data,
            action_prefix + macb_type.lower(),
        )
        records.append(timeline_record)

    return records


def format_timeline_records(
    record: dict, filepath: str, mft_file_path: str, tags: Optional[List[str]] = None
) -> List[dict]:
    timeline_records = []
    context = None

    for attribute in record.get("attributes", []):
        attr_type = attribute.get("header", {}).get("type_code")
        if attr_type not in TIMELINE_ATTRIBUTES:
            continue
        if "data" not in attribute:
            continue
        if context is None:
            context = _timeline_record_context(record, filepath, tags)
        macb_records = _macb_records_for_attribute(
            record, attribute, attr_type, mft_file_path, context
        )
        timeline_records.extend(macb_records)

    return timeline_records


def format_standard_record(
    record: dict, filepath: str, tags: Optional[List[str]] = None
) -> dict:
    base_tags = build_tags(tags)

    attributes = {}
    for attribute in record.get("attributes"):
        attributes[attribute.get("header").get("type_code")] = attribute
    record["attributes"] = attributes

    if "FileName" in record["attributes"]:
        filepath = filepath
        record["attributes"]["FileName"]["data"]["path"] = filepath

    for v in ("DATA", "BITMAP"):
        for attribute in ("vnc_first", "vnc_last"):
            vnc = (
                record.get("attributes", dict())
                .get(v, dict())
                .get("header", dict())
                .get("residential_header", dict())
                .get(attribute)
            )
            if vnc:
                record["attributes"][v]["header"]["residential_header"][attribute] = (
                    hex(vnc)
                )

    record["tags"] = base_tags

    return record


def process_standard_by_chunk(
    records: List[Union[str, Exception]],
    rows: List[Union[bytes, Exception]],
    tags: TagsInput = None,
    diagnostics: Optional[List[dict]] = None,
    record_offset: int = 0,
) -> List[dict]:
    return _process_chunk(records, rows, "", False, tags, diagnostics, record_offset)


def process_timeline_by_chunk(
    records: List[Union[str, Exception]],
    rows: List[Union[bytes, Exception]],
    mft_file_path: str,
    tags: TagsInput = None,
    diagnostics: Optional[List[dict]] = None,
    record_offset: int = 0,
) -> List[dict]:
    return _process_chunk(
        records, rows, mft_file_path, True, tags, diagnostics, record_offset
    )


def _process_chunk(
    records, rows, mft_file_path, timeline_mode, tags, diagnostics, record_offset
):
    if len(records) != len(rows):
        raise RuntimeError("MFT JSON and CSV chunk lengths do not match")
    parsed_tags = parse_tags(tags)
    output = []
    # Native iterators can yield Exception objects. Never filter either stream
    # independently: the paired item must be discarded from both streams.
    for index, (raw_record, row) in enumerate(zip(records, rows), record_offset):
        record_number = None
        native_diagnostics = []
        if isinstance(raw_record, NativeRecord):
            native_diagnostics.extend(raw_record.diagnostics)
            raw_record = raw_record.value
        if isinstance(row, NativeRecord):
            native_diagnostics.extend(row.diagnostics)
            row = row.value
        if isinstance(raw_record, Exception):
            _record_pair_error(diagnostics, index, record_number, "parse", raw_record)
            continue
        try:
            record = orjson.loads(raw_record)
            record_number = record.get("header", {}).get("record_number")
        except Exception as error:
            if isinstance(row, Exception):
                _record_pair_error(diagnostics, index, record_number, "parse", row)
            else:
                _record_pair_error(diagnostics, index, record_number, "json", error)
            continue
        for stage, error in native_diagnostics:
            _record_pair_error(diagnostics, index, record_number, stage, error)
        # Decode JSON first so a CSV failure retains the known record number.
        # Native error values must not be raised: adding tracebacks would form
        # cycles through the input chunk and retain the thread-affine parsers.
        if isinstance(row, Exception):
            _record_pair_error(diagnostics, index, record_number, "parse", row)
            continue
        try:
            stage = "csv"
            filename = filename_from_csv_blob(row, record_number)
            stage = "normalize"
            if timeline_mode:
                # Build all MACB records before publishing any from this record.
                converted = format_timeline_records(
                    record, filename, mft_file_path, parsed_tags
                )
            else:
                converted = [format_standard_record(record, filename, parsed_tags)]
        except Exception as error:
            _record_pair_error(diagnostics, index, record_number, stage, error)
            continue
        output.extend(converted)
    return output


def _record_pair_error(diagnostics, index, record_number, stage, error):
    diagnostic = {
        "record_index": index,
        "record_number": record_number,
        "stage": stage,
        "error": (
            error if isinstance(error, str) else f"{type(error).__name__}: {error}"
        ),
    }
    if diagnostics is not None:
        diagnostics.append(diagnostic)
    else:
        logger.warning(
            "Could not fully extract MFT record at iterator index %d (%s): %s",
            index,
            stage,
            diagnostic["error"],
        )


def _mp_worker(args):
    json_chunk, csv_chunk, mft_file_path, timeline_mode, tags, record_offset = args
    diagnostics = []
    if timeline_mode:
        records = process_timeline_by_chunk(
            json_chunk, csv_chunk, mft_file_path, tags, diagnostics, record_offset
        )
    else:
        records = process_standard_by_chunk(
            json_chunk, csv_chunk, tags, diagnostics, record_offset
        )
    return records, diagnostics


class Mft2es(SafeMultiprocessingMixin):
    def __init__(self, input_path: Path) -> None:
        self.path = Path(input_path).resolve()
        self.diagnostics = []
        self._file_handle_json = None
        self._file_handle_csv = None
        self.parser = None
        self.csvparser = None
        self._json_reader = None
        self._csv_reader = None
        try:
            self._file_handle_json = self.path.open(mode="rb")
            self._file_handle_csv = self.path.open(mode="rb")
            self._json_reader = MftRecordReader(
                self._file_handle_json, inspect_attributes=True
            )
            self._csv_reader = MftRecordReader(
                self._file_handle_csv, detect_path_cycles=True
            )
            self.parser = PyMftParser(self._json_reader)
            self.csvparser = PyMftParser(self._csv_reader)
        except BaseException:
            # Do not leave a thread-affine parser reachable from the exception's
            # constructor frame until a later, possibly foreign-thread GC.
            self.parser = None
            self.csvparser = None
            self.close()
            raise

    def close(self):
        if self._file_handle_json is not None:
            self._file_handle_json.close()
        if self._file_handle_csv is not None:
            self._file_handle_csv.close()

    def _collect_result(self, result):
        records, diagnostics = result
        for diagnostic in diagnostics:
            diagnostic = {"source_file": str(self.path), **diagnostic}
            self.diagnostics.append(diagnostic)
            logger.warning(
                "Could not fully extract MFT record from %s at iterator index %d (%s): %s",
                self.path,
                diagnostic["record_index"],
                diagnostic["stage"],
                diagnostic["error"],
            )
        return records

    def _record_tasks(self, chunk_size, timeline_mode, tags):
        # Both native streams are thread-affine and must advance together here.
        pairs = zip_longest(
            generate_chunks(
                chunk_size,
                native_records(
                    self.parser.entries_json(), getattr(self, "_json_reader", None)
                ),
            ),
            generate_chunks(
                chunk_size,
                native_records(
                    self.csvparser.entries_csv(), getattr(self, "_csv_reader", None)
                ),
            ),
        )
        for chunk_index, (json_chunk, csv_chunk) in enumerate(pairs):
            if json_chunk is None or csv_chunk is None:
                raise RuntimeError("MFT JSON and CSV record counts do not match")
            yield (
                json_chunk,
                csv_chunk,
                str(self.path),
                timeline_mode,
                tags,
                chunk_index * chunk_size,
            )

    def gen_timeline_records(
        self,
        multiprocess: bool,
        chunk_size: int,
        timeline_mode: bool = True,
        tags: TagsInput = None,
    ) -> Generator:
        validate_chunk_size(chunk_size)
        self.diagnostics = []
        tasks = self._record_tasks(chunk_size, timeline_mode, tags)
        if multiprocess:
            ctx = self.get_multiprocessing_context()
            workers = max(1, self.get_cpu_count())
            with ctx.Pool(workers) as pool:
                for result in ordered_pool_results(
                    pool, _mp_worker, tasks, workers * 2
                ):
                    yield self._collect_result(result)
        else:
            for task in tasks:
                yield self._collect_result(_mp_worker(task))
