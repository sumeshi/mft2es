# coding: utf-8
from typing import List
from pathlib import Path

from mft2es.models.Mft2es import Mft2es
from mft2es.presenters.Mft2esPresenter import Mft2esPresenter


# for use via python-script!

def mft2es(
    input_path: str,
    host: str = "localhost",
    port: int = 9200,
    index: str = "mft2es",
    scheme: str = "http",
    pipeline: str = "",
    login: str = "",
    pwd: str = "",
    multiprocess: bool = False,
    chunk_size: int = 500
) -> None:
    """Fast import of Windows MFT into Elasticsearch.
    Args:
        input_path (str):
            Windows MFTs to import into Elasticsearch.

        host (str, optional):
            Elasticsearch host address. Defaults to "localhost".

        port (int, optional):
            Elasticsearch port number. Defaults to 9200.

        index (str, optional):
            Name of the index to create. Defaults to "mft2es".

        scheme (str, optional):
            Elasticsearch address scheme. Defaults to "http".

        pipeline (str, optional):
            Elasticsearch Ingest Pipeline. Defaults to "".

        login (str, optional):
            Elasticsearch login to connect into.

        pwd (str, optional):
            Elasticsearch password associated with the login provided.

        multiprocess (bool, optional):
            Flag to run multiprocessing.

        chunk_size (int, optional):
            Size of the chunk to be processed for each process.
    """

    mp = Mft2esPresenter(
        input_path=Path(input_path),
        host=host,
        port=int(port),
        index=index,
        scheme=scheme,
        pipeline=pipeline,
        login=login,
        pwd=pwd,
        is_quiet=True,
        multiprocess=multiprocess,
        chunk_size=int(chunk_size),
    ).bulk_import()


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
