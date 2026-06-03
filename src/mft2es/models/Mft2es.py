# coding: utf-8
import ntpath
import sys
import os
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Sequence, Union
from itertools import islice
import multiprocessing as mp

import orjson
from mft import PyMftParser

# Constants for timeline analysis
MACB_MAPPING = {"M": "modified", "A": "accessed", "C": "mft_modified", "B": "created"}

# Target attributes for timeline analysis
TIMELINE_ATTRIBUTES = ["StandardInformation", "FileName"]
TagsInput = Optional[Union[str, Sequence[str]]]


def parse_tags(tags: TagsInput) -> List[str]:
    if not tags:
        return []
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    if isinstance(tags, Sequence):
        return [t.strip() for t in tags if t and t.strip()]
    return []


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
    i = iter(iterable)
    piece = list(islice(i, chunk_size))
    while piece:
        yield piece
        piece = list(islice(i, chunk_size))


def organize_attributes_by_type(record: dict) -> Dict[str, dict]:
    attributes = {}
    for attribute in record.get("attributes", []):
        type_code = attribute.get("header", {}).get("type_code")
        if type_code:
            attributes[type_code] = attribute
    return attributes


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
    base_tags = ["mft"] + (tags or [])

    attr_data = attribute.get("data", {})
    record_header = record.get("header", {})
    attr_header = attribute.get("header", {})

    return {
        "@timestamp": attr_data.get(timestamp_field),
        "event": {
            "action": f"mft-{attr_type.lower()}-{macb_type.lower()}",
            "category": ["file"],
            "type": ["change"],
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
    attributes = organize_attributes_by_type(record)
    timeline_records = []

    for attr_type in TIMELINE_ATTRIBUTES:
        attribute = attributes.get(attr_type, {})
        macb_records = create_macb_records_for_attribute(
            record, attribute, attr_type, filepath, mft_file_path, tags
        )
        timeline_records.extend(macb_records)

    return timeline_records


def format_standard_record(
    record: dict, filepath: str, tags: Optional[List[str]] = None
) -> dict:
    base_tags = ["mft"] + (tags or [])

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
    filename_list: List[str] = [
        row.decode("utf-8").split(",")[-1].strip() for row in rows
    ]

    record_list: List[dict] = [orjson.loads(r) for r in records]
    parsed_tags = parse_tags(tags)

    return [
        format_standard_record(record, filename, parsed_tags)
        for record, filename in zip(record_list, filename_list)
    ]


def process_timeline_by_chunk(
    records: List[str], rows: List[bytes], mft_file_path: str, tags: TagsInput = None
) -> List[dict]:
    filename_list: List[str] = [
        row.decode("utf-8").split(",")[-1].strip() for row in rows
    ]

    record_list: List[dict] = [orjson.loads(r) for r in records]
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
        self.path = input_path
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
        if multiprocess:
            ctx = self.get_multiprocessing_context()
            with ctx.Pool(self.get_cpu_count()) as pool:
                yield from pool.imap(
                    _mp_worker,
                    (
                        (j, c, str(self.path), timeline_mode, tags)
                        for j, c in zip(
                            generate_chunks(chunk_size, self.parser.entries_json()),
                            generate_chunks(chunk_size, self.csvparser.entries_csv()),
                        )
                    ),
                )
        else:
            for json_chunk, csv_chunk in zip(
                generate_chunks(chunk_size, self.parser.entries_json()),
                generate_chunks(chunk_size, self.csvparser.entries_csv()),
            ):
                if timeline_mode:
                    yield process_timeline_by_chunk(
                        json_chunk, csv_chunk, str(self.path), tags
                    )
                else:
                    yield process_standard_by_chunk(json_chunk, csv_chunk, tags)
