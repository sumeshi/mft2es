# coding: utf-8
import sys
import os
from itertools import chain
from pathlib import Path
from typing import List, Generator, Iterable
from itertools import islice
import multiprocessing as mp

import orjson
from mft import PyMftParser

class SafeMultiprocessingMixin:
    """Safe multiprocessing management class for Python 3.13 compatibility"""
    
    @staticmethod
    def get_multiprocessing_context() -> mp.context.BaseContext:
        """Get safe multiprocessing context"""
        # Use spawn for Python 3.13+ or test environments to avoid fork() issues
        if sys.version_info >= (3, 13) or 'pytest' in sys.modules:
            try:
                ctx = mp.get_context('spawn')
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


def format_record(record: dict, filepath: str):
    """Formatting each MFT records.

    Args:
        records (List[str]): chunk of MFT records(json).
        filepath str: file full path.

    Yields:
        List[dict]: MFT records.
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
                record["attributes"][v]["header"]["residential_header"][
                    attribute
                ] = hex(vnc)

    return record


def process_by_chunk(records: List[str], rows: List[bytes]) -> List[dict]:
    """Perform formatting for each chunk. (for efficiency)

    Args:
        records (List[str]): chunk of MFT records(json).
        rows (List[bytes]): chunk of MFT records(csv).

    Yields:
        List[dict]: MFT records list.
    """

    filename_list: List[str] = [
        row.decode("utf-8").split(",")[-1].strip() for row in rows
    ]

    concatenated_json: str = f"[{','.join(records)}]"
    record_list: List[dict] = orjson.loads(concatenated_json)

    return [
        format_record(record, filename) for record, filename in zip(record_list, filename_list)
    ]


class Mft2es(SafeMultiprocessingMixin):
    def __init__(self, input_path: Path) -> None:
        self.path = input_path
        self.parser = PyMftParser(self.path.open(mode="rb"))
        self.csvparser = PyMftParser(self.path.open(mode="rb"))

    def gen_records(self, multiprocess: bool, chunk_size: int) -> Generator:
        """Generates the formatted MFT records chunks.

        Args:
            multiprocess (bool): Flag to run multiprocessing.
            chunk_size (int): Size of the chunk to be processed for each process.

        Yields:
            Generator: Yields List[dict].
        """

        if multiprocess:
            # Use safe context for Python 3.13 compatibility
            ctx = self.get_multiprocessing_context()
            with ctx.Pool(self.get_cpu_count()) as pool:
                results = pool.starmap_async(process_by_chunk, zip(generate_chunks(chunk_size, self.parser.entries_json()), generate_chunks(chunk_size, self.csvparser.entries_csv())))
                yield list(chain.from_iterable(results.get(timeout=None)))
        else:
            buffer: List[dict] = list()
            for json, csv in zip(
                generate_chunks(chunk_size, self.parser.entries_json()), generate_chunks(chunk_size, self.csvparser.entries_csv())
            ):
                if chunk_size <= len(buffer):
                    yield list(chain.from_iterable(buffer))
                    buffer.clear()
                else:
                    buffer.append(process_by_chunk(json, csv))
            else:
                yield list(chain.from_iterable(buffer))
