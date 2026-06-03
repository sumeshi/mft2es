# coding: utf-8
from typing import List, Optional
from pathlib import Path

from mft2es.__about__ import __version__
from mft2es.models.Mft2es import Mft2es
from mft2es.presenters.Mft2esPresenter import Mft2esPresenter

__all__ = ["__version__", "mft2es", "mft2json"]


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
    chunk_size: int = 500,
    timeline_mode: bool = False,
    additional_tags: Optional[List[str]] = None,
    verify_certs: bool = True,
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

        timeline_mode (bool, optional):
            Enable timeline analysis mode - creates specialized records
            for Standard Information, Filename, and attributes.

        additional_tags (Optional[List[str]], optional):
            Comma-separated tags as a list to add to each record
            (e.g., ['WORKSTATION-1', 'DOMAIN-ABC']).

        verify_certs (bool, optional):
            Verify SSL/TLS certificates when connecting to Elasticsearch.
    """

    Mft2esPresenter(
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
        timeline_mode=timeline_mode,
        tags=additional_tags,
        verify_certs=verify_certs,
    ).bulk_import()


def mft2json(
    filepath: str,
    multiprocess: bool = False,
    chunk_size: int = 500,
    timeline_mode: bool = False,
    additional_tags: Optional[List[str]] = None,
) -> List[dict]:
    """Convert Windows MFT to List[dict].

    Args:
        filepath (str): Input MFT file.
        multiprocess (bool): Flag to run multiprocessing.
        chunk_size (int): Size of the chunk to be processed for each process.
        timeline_mode (bool): Enable timeline analysis mode - creates specialized records.
        additional_tags (Optional[List[str]], optional):
            Comma-separated tags as a list to add to each record
            (e.g., ['WORKSTATION-1', 'DOMAIN-ABC']).

    Note:
        Since the content of the file is loaded into memory at once,
        it requires the same amount of memory as the file to be loaded.
    """
    mft = Mft2es(Path(filepath).resolve())
    try:
        records: List[dict] = sum(
            list(
                mft.gen_timeline_records(
                    multiprocess=multiprocess,
                    chunk_size=chunk_size,
                    timeline_mode=timeline_mode,
                    tags=additional_tags,
                )
            ),
            list(),
        )
        return records
    finally:
        mft.close()
