#!/usr/bin/env python3
# coding: utf-8

import argparse
import traceback
from hashlib import sha1
from pathlib import Path
from typing import List, Generator

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

import orjson
from tqdm import tqdm






def mft2es(
    filepath: str,
    host: str = "localhost",
    port: int = 9200,
    index: str = "mft2es",
    size: int = 500,
    scheme: str = "http",
    pipeline: str = "",
    login: str = "",
    pwd: str = ""
):
    """Fast import of Windows MFT into Elasticsearch.
    Args:
        filepath (str):
            Windows MFTs to import into Elasticsearch.

        host (str, optional):
            Elasticsearch host address. Defaults to "localhost".

        port (int, optional):
            Elasticsearch port number. Defaults to 9200.

        index (str, optional):
            Name of the index to create. Defaults to "mft2es".

        size (int, optional):
            Buffer size for BulkIndice at a time. Defaults to 500.

        scheme (str, optional):
            Elasticsearch address scheme. Defaults to "http".

        pipeline (str, optional):
            Elasticsearch Ingest Pipeline. Defaults to "".

        login (str, optional):
            Elasticsearch login to connect into.

        pwd (str, optional):
            Elasticsearch password associated with the login provided.
    """
    es = ElasticsearchUtils(hostname=host, port=port, scheme=scheme, login=login, pwd=pwd)
    r = Mft2es(filepath)

    for records in tqdm(r.gen_records(size)):
        try:
            es.bulk_indice(records, index, pipeline)
        except Exception:
            traceback.print_exc()






def console_mft2es():
    """ This function is loaded when used from the console.
    """

    # Args
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mftfiles",
        nargs="+",
        type=Path,
        help="Windows MFT or directories containing them. (filename must be set 'MFT', or '$MFT')",
    )

    # Options
    parser.add_argument("--host", default="localhost", help="ElasticSearch host")
    parser.add_argument("--port", default=9200, help="ElasticSearch port number")
    parser.add_argument("--index", default="mft2es", help="Index name")
    parser.add_argument("--size", default=500, help="Bulk insert buffer size")
    parser.add_argument("--scheme", default="http", help="Scheme to use (http, https)")
    parser.add_argument("--pipeline", default="", help="Ingest pipeline to use")
    parser.add_argument("--login", default="", help="Login to use to connect to Elastic database")
    parser.add_argument("--pwd", default="", help="Password associated with the login")
    args = parser.parse_args()

    # Target files
    mftfiles = list()
    for mftfile in args.mftfiles:
        if mftfile.is_dir():
            mftfiles.extend(mftfile.glob("**/mft"))
            mftfiles.extend(mftfile.glob("**/MFT"))
            mftfiles.extend(mftfile.glob("**/$MFT"))
        else:
            mftfiles.append(mftfile)

    # Indexing MFT files
    for mftfile in mftfiles:
        print(f"Currently Importing {mftfile}")
        mft2es(
            filepath=mftfile,
            host=args.host,
            port=int(args.port),
            index=args.index,
            size=int(args.size),
            scheme=args.scheme,
            pipeline=args.pipeline,
            login=args.login,
            pwd=args.pwd
        )
        print()

    print("Import completed.")


if __name__ == "__main__":
    console_mft2es()
