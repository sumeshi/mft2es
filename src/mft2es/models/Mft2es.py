# coding: utf-8
import sys
import os
from itertools import chain
from pathlib import Path
from typing import List, Generator, Iterable, Dict
from itertools import islice
import multiprocessing as mp

import orjson
from mft import PyMftParser

# Constants for timeline analysis
MACB_MAPPING = {"M": "modified", "A": "accessed", "C": "mft_modified", "B": "created"}

# Target attributes for timeline analysis
TIMELINE_ATTRIBUTES = ["StandardInformation", "FileName"]


class SafeMultiprocessingMixin:
    """Safe multiprocessing management class for Python 3.13 compatibility"""

    @staticmethod
    def get_multiprocessing_context() -> mp.context.BaseContext:
        """Get safe multiprocessing context"""
        # Use spawn for Python 3.13+ or test environments to avoid fork() issues
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
        """Get CPU count safely"""
        try:
            return mp.cpu_count()
        except NotImplementedError:
            return os.cpu_count() or 1


def generate_chunks(chunk_size: int, iterable: Iterable) -> Generator:
    """Generate arbitrarily sized chunks from iterable objects.

    Args:
        chunk_size (int): Chunk sizes.
        iterable (Iterable): Original Iterable object.

    Yields:
        Generator: List
    """
    i = iter(iterable)
    piece = list(islice(i, chunk_size))
    while piece:
        yield piece
        piece = list(islice(i, chunk_size))


def organize_attributes_by_type(record: dict) -> Dict[str, dict]:
    """Organize MFT record attributes by type code.

    Args:
        record (dict): Single MFT record

    Returns:
        Dict[str, dict]: Attributes organized by type code
    """
    attributes = {}
    for attribute in record.get("attributes", []):
        type_code = attribute.get("header", {}).get("type_code")
        if type_code:
            attributes[type_code] = attribute
    return attributes


def extract_file_info(filepath: str) -> Dict[str, str]:
    """Extract file information from filepath.

    Args:
        filepath (str): File full path

    Returns:
        Dict[str, str]: File information
    """
    return {"path": filepath, "name": filepath.split("/")[-1] if filepath else ""}


def create_timeline_record(
    record: dict,
    attribute: dict,
    attr_type: str,
    macb_type: str,
    timestamp_field: str,
    filepath: str,
) -> dict:
    """Create a single timeline record for MACB analysis.

    Args:
        record (dict): Original MFT record
        attribute (dict): Attribute data
        attr_type (str): Attribute type (StandardInformation or FileName)
        macb_type (str): MACB type (M, A, C, B)
        timestamp_field (str): Timestamp field name
        filepath (str): File full path

    Returns:
        dict: Timeline record
    """
    attr_data = attribute.get("data", {})
    record_header = record.get("header", {})
    attr_header = attribute.get("header", {})

    return {
        "@timestamp": attr_data.get(timestamp_field),
        "record_number": record_header.get("record_number", 0),
        "mft": {
            "header": {k: v for k, v in record_header.items() if k != "record_number"}
        },
        "attribute": {
            "type": attr_type,
            "macb_type": macb_type,
            "header": {k: v for k, v in attr_header.items() if k != "type_code"},
            "data": {
                k: v for k, v in attr_data.items() if k not in MACB_MAPPING.values()
            },
        },
        "file": extract_file_info(filepath),
    }


def create_macb_records_for_attribute(
    record: dict, attribute: dict, attr_type: str, filepath: str
) -> List[dict]:
    """Create MACB records for a single attribute.

    Args:
        record (dict): Original MFT record
        attribute (dict): Attribute data
        attr_type (str): Attribute type
        filepath (str): File full path

    Returns:
        List[dict]: MACB timeline records for the attribute
    """
    if not attribute or "data" not in attribute:
        return []

    records = []
    for macb_type, timestamp_field in MACB_MAPPING.items():
        timeline_record = create_timeline_record(
            record, attribute, attr_type, macb_type, timestamp_field, filepath
        )
        records.append(timeline_record)

    return records


def format_timeline_records(record: dict, filepath: str) -> List[dict]:
    """Format MFT record into timeline analysis records.

    Creates MACB timeline records for StandardInformation and FileName attributes.

    Args:
        record (dict): Single MFT record
        filepath (str): File full path

    Returns:
        List[dict]: Timeline records (MACB for StandardInformation and FileName)
    """
    attributes = organize_attributes_by_type(record)
    timeline_records = []

    # Create MACB records for each target attribute type
    for attr_type in TIMELINE_ATTRIBUTES:
        attribute = attributes.get(attr_type, {})
        macb_records = create_macb_records_for_attribute(
            record, attribute, attr_type, filepath
        )
        timeline_records.extend(macb_records)

    return timeline_records


def format_standard_record(record: dict, filepath: str) -> dict:
    """Format MFT record into standard format.

    Args:
        record (dict): Single MFT record
        filepath (str): File full path

    Returns:
        dict: Standard MFT record
    """

    attributes = {}
    for attribute in record.get("attributes"):
        attributes[attribute.get("header").get("type_code")] = attribute
    record["attributes"] = attributes

    # entries_json method does not include the information of full path... :(
    if "FileName" in record["attributes"]:
        filepath = filepath
        record["attributes"]["FileName"]["data"]["path"] = filepath

    for v in (
        "DATA",
        "BITMAP",
    ):
        for attribute in (
            "vnc_first",
            "vnc_last",
        ):
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

    return record


def process_standard_by_chunk(records: List[str], rows: List[bytes]) -> List[dict]:
    """Process standard MFT records by chunk.

    Args:
        records (List[str]): chunk of MFT records(json).
        rows (List[bytes]): chunk of MFT records(csv).

    Returns:
        List[dict]: MFT records list.
    """

    filename_list: List[str] = [
        row.decode("utf-8").split(",")[-1].strip() for row in rows
    ]

    concatenated_json: str = f"[{','.join(records)}]"
    record_list: List[dict] = orjson.loads(concatenated_json)

    return [
        format_standard_record(record, filename)
        for record, filename in zip(record_list, filename_list)
    ]


def process_timeline_by_chunk(records: List[str], rows: List[bytes]) -> List[dict]:
    """Perform timeline formatting for each chunk.

    Creates multiple specialized records per MFT entry for better analysis.

    Args:
        records (List[str]): chunk of MFT records(json).
        rows (List[bytes]): chunk of MFT records(csv).

    Returns:
        List[dict]: Multiple specialized timeline records per MFT entry.
    """

    filename_list: List[str] = [
        row.decode("utf-8").split(",")[-1].strip() for row in rows
    ]

    concatenated_json: str = f"[{','.join(records)}]"
    record_list: List[dict] = orjson.loads(concatenated_json)

    timeline_records = []
    for record, filename in zip(record_list, filename_list):
        timeline_records.extend(format_timeline_records(record, filename))

    return timeline_records


class Mft2es(SafeMultiprocessingMixin):
    def __init__(self, input_path: Path) -> None:
        self.path = input_path
        self.parser = PyMftParser(self.path.open(mode="rb"))
        self.csvparser = PyMftParser(self.path.open(mode="rb"))

    def gen_timeline_records(
        self, multiprocess: bool, chunk_size: int, timeline_mode: bool = False
    ) -> Generator:
        """Generates MFT records.

        Args:
            multiprocess (bool): Flag to run multiprocessing.
            chunk_size (int): Size of the chunk to be processed for each process.
            timeline_mode (bool): Flag to enable timeline analysis mode.

        Yields:
            Generator: Yields List[dict].
        """

        if multiprocess:
            # Use safe context for Python 3.13 compatibility
            ctx = self.get_multiprocessing_context()
            if timeline_mode:
                with ctx.Pool(self.get_cpu_count()) as pool:
                    results = pool.starmap_async(
                        process_timeline_by_chunk,
                        zip(
                            generate_chunks(chunk_size, self.parser.entries_json()),
                            generate_chunks(chunk_size, self.csvparser.entries_csv()),
                        ),
                    )
                    yield list(chain.from_iterable(results.get(timeout=None)))
            else:
                with ctx.Pool(self.get_cpu_count()) as pool:
                    results = pool.starmap_async(
                        process_standard_by_chunk,
                        zip(
                            generate_chunks(chunk_size, self.parser.entries_json()),
                            generate_chunks(chunk_size, self.csvparser.entries_csv()),
                        ),
                    )
                    yield list(chain.from_iterable(results.get(timeout=None)))
        else:
            buffer: List[dict] = list()
            for json, csv in zip(
                generate_chunks(chunk_size, self.parser.entries_json()),
                generate_chunks(chunk_size, self.csvparser.entries_csv()),
            ):
                if chunk_size <= len(buffer):
                    yield list(chain.from_iterable(buffer))
                    buffer.clear()
                else:
                    if timeline_mode:
                        buffer.append(process_timeline_by_chunk(json, csv))
                    else:
                        buffer.append(process_standard_by_chunk(json, csv))
            else:
                yield list(chain.from_iterable(buffer))
