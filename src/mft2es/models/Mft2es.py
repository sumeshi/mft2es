# coding: utf-8
import ntpath
import sys
import os
import csv
import io
from pathlib import Path
from typing import Generator, Iterable, List, Optional, Sequence, Union
from itertools import islice, zip_longest
import multiprocessing as mp
from collections import deque

import orjson
from mft import PyMftParser

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
        if (
            len(row) > entry_id_column
            and row[entry_id_column].strip() == str(record_number)
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


class SafeMultiprocessingMixin:
    """Safe multiprocessing management class for Python 3.13 compatibility"""

    @staticmethod
    def get_multiprocessing_context() -> mp.context.BaseContext:
        """Get safe multiprocessing context"""
        if sys.version_info >= (3, 13) or "pytest" in sys.modules:
            try:
                ctx = mp.get_context("spawn")
            except RuntimeError:
                ctx = mp.get_context()
        else:
            ctx = mp.get_context()

        return ctx

    @staticmethod
    def get_cpu_count() -> int:
        try:
            return mp.cpu_count()
        except NotImplementedError:
            return os.cpu_count() or 1


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
    base_tags = build_tags(tags)

    attr_data = attribute.get("data", {})
    record_header = record.get("header", {})
    attr_header = attribute.get("header", {})

    return {
        "@timestamp": attr_data.get(timestamp_field),
        "event": {
            "action": f"mft-{attr_type.lower()}-{macb_type.lower()}",
            "category": ["file"],
            "type": [MACB_EVENT_TYPE_MAPPING[macb_type]],
            "kind": "event",
            "provider": "mft",
            "module": "windows",
            "dataset": "windows.mft",
        },
        "windows": {
            "mft": {
                "record": {
                    "number": record_header.get("record_number", 0),
                    "name": ntpath.basename(filepath) if filepath else "",
                    "path": filepath,
                },
                "header": {
                    k: v for k, v in record_header.items() if k != "record_number"
                },
                "attribute": {
                    "type": attr_type,
                    "macb_type": macb_type,
                    "header": {
                        k: v for k, v in attr_header.items() if k != "type_code"
                    },
                    "data": {
                        k: v
                        for k, v in attr_data.items()
                        if k not in MACB_MAPPING.values()
                    },
                },
            },
        },
        "log": {"file": {"path": mft_file_path}},
        "tags": base_tags,
    }


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

    records = []
    for macb_type, timestamp_field in MACB_MAPPING.items():
        timeline_record = create_timeline_record(
            record,
            attribute,
            attr_type,
            macb_type,
            timestamp_field,
            filepath,
            mft_file_path,
            tags,
        )
        records.append(timeline_record)

    return records


def format_timeline_records(
    record: dict, filepath: str, mft_file_path: str, tags: Optional[List[str]] = None
) -> List[dict]:
    timeline_records = []

    for attribute in record.get("attributes", []):
        attr_type = attribute.get("header", {}).get("type_code")
        if attr_type not in TIMELINE_ATTRIBUTES:
            continue
        macb_records = create_macb_records_for_attribute(
            record, attribute, attr_type, filepath, mft_file_path, tags
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
    records: List[str], rows: List[bytes], tags: TagsInput = None
) -> List[dict]:
    record_list: List[dict] = [orjson.loads(r) for r in records]
    if len(record_list) != len(rows):
        raise RuntimeError("MFT JSON and CSV chunk lengths do not match")
    filename_list = [
        filename_from_csv_blob(row, record.get("header", {}).get("record_number"))
        for record, row in zip(record_list, rows)
    ]
    parsed_tags = parse_tags(tags)

    return [
        format_standard_record(record, filename, parsed_tags)
        for record, filename in zip(record_list, filename_list)
    ]


def process_timeline_by_chunk(
    records: List[str], rows: List[bytes], mft_file_path: str, tags: TagsInput = None
) -> List[dict]:
    record_list: List[dict] = [orjson.loads(r) for r in records]
    if len(record_list) != len(rows):
        raise RuntimeError("MFT JSON and CSV chunk lengths do not match")
    filename_list = [
        filename_from_csv_blob(row, record.get("header", {}).get("record_number"))
        for record, row in zip(record_list, rows)
    ]
    parsed_tags = parse_tags(tags)

    timeline_records = []
    for record, filename in zip(record_list, filename_list):
        timeline_records.extend(
            format_timeline_records(record, filename, mft_file_path, parsed_tags)
        )

    return timeline_records


def _mp_worker(args):
    json_chunk, csv_chunk, mft_file_path, timeline_mode, tags = args
    if timeline_mode:
        return process_timeline_by_chunk(json_chunk, csv_chunk, mft_file_path, tags)
    return process_standard_by_chunk(json_chunk, csv_chunk, tags)


class Mft2es(SafeMultiprocessingMixin):
    def __init__(self, input_path: Path) -> None:
        self.path = Path(input_path).resolve()
        self._file_handle_json = self.path.open(mode="rb")
        self._file_handle_csv = self.path.open(mode="rb")
        self.parser = PyMftParser(self._file_handle_json)
        self.csvparser = PyMftParser(self._file_handle_csv)

    def close(self):
        self._file_handle_json.close()
        self._file_handle_csv.close()

    def gen_timeline_records(
        self,
        multiprocess: bool,
        chunk_size: int,
        timeline_mode: bool = False,
        tags: TagsInput = None,
    ) -> Generator:
        validate_chunk_size(chunk_size)
        if multiprocess:
            ctx = self.get_multiprocessing_context()
            workers = self.get_cpu_count()
            with ctx.Pool(workers) as pool:
                # imap consumes its iterable on the pool's task-handler thread.
                # PyMft iterators are thread-affine: consume them here and send
                # only materialized Python chunks to workers. Bound prefetch to
                # avoid retaining the entire MFT, and preserve input order.
                pending = deque()
                for j, c in zip_longest(
                    generate_chunks(chunk_size, self.parser.entries_json()),
                    generate_chunks(chunk_size, self.csvparser.entries_csv()),
                ):
                    if j is None or c is None:
                        raise RuntimeError("MFT JSON and CSV record counts do not match")
                    pending.append(pool.apply_async(
                        _mp_worker, ((j, c, str(self.path), timeline_mode, tags),)
                    ))
                    if len(pending) >= workers * 2:
                        yield pending.popleft().get()
                while pending:
                    yield pending.popleft().get()
        else:
            for json_chunk, csv_chunk in zip_longest(
                generate_chunks(chunk_size, self.parser.entries_json()),
                generate_chunks(chunk_size, self.csvparser.entries_csv()),
            ):
                if json_chunk is None or csv_chunk is None:
                    raise RuntimeError("MFT JSON and CSV record counts do not match")
                if timeline_mode:
                    yield process_timeline_by_chunk(
                        json_chunk, csv_chunk, str(self.path), tags
                    )
                else:
                    yield process_standard_by_chunk(json_chunk, csv_chunk, tags)
