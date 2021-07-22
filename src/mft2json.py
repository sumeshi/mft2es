# coding: utf-8
from typing import List
from pathlib import Path

from models.Mft2es import Mft2es


# for use via python-script!

def mft2json(filepath: str, multiprocess: bool = False, chunk_size: int = 500) -> List[dict]:
    """Convert Windows MFT to List[dict].

    Args:
        filepath (str): Input MFT file.
        multiprocess (bool): Flag to run multiprocessing.
        chunk_size (int): Size of the chunk to be processed for each process.

    Note:
        Since the content of the file is loaded into memory at once,
        it requires the same amount of memory as the file to be loaded.
    """
    mft = Mft2es(Path(filepath).resolve())
    records: List[dict] = sum(list(mft.gen_records(multiprocess=multiprocess, chunk_size=chunk_size)), list())

    return records
