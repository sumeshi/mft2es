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
from mft import PyMftParser
from tqdm import tqdm


class ElasticsearchUtils(object):
    def __init__(self, hostname: str, port: int, scheme: str, login: str, pwd: str) -> None:
        if login == "":
            self.es = Elasticsearch(host=hostname, port=port, scheme=scheme, verify_certs=False)
        else:
            self.es = Elasticsearch(host=hostname, port=port, scheme=scheme, verify_certs=False, http_auth=(login, pwd))

    def calc_hash(self, record: dict) -> str:
        """Calculate hash value from record.
        Args:
            record (dict): MFT record.
        Returns:
            str: Hash value
        """
        return sha1(orjson.dumps(record, option=orjson.OPT_SORT_KEYS)).hexdigest()

    def bulk_indice(self, records, index_name: str, pipeline: str) -> None:
        """Bulk indices the documents into Elasticsearch.
        Args:
            records (List[dict]): List of each records read from MFT files.
            index_name (str): Target Elasticsearch Index.
            pipeline (str): Target Elasticsearch Ingest Pipeline
        """
        events = []
        for record in records:
            event = {"_id": self.calc_hash(record), "_index": index_name, "_source": record}
            if pipeline != "":
                event["pipeline"] = pipeline
            events.append(event)
        bulk(self.es, events, raise_on_error=False)


class Mft2es(object):
    def __init__(self, filepath: str) -> None:
        self.path = Path(filepath)
        self.parser = PyMftParser(self.path.open(mode="rb"))
        self.csvparser = PyMftParser(self.path.open(mode="rb"))

    def gen_records(self, size: int) -> Generator:
        """A generator that reads records from an MFT file and generates a dict for each record.
        Args:
            size (int): Buffer size.
        Yields:
            Generator: Yields List[dict].
        """

        buffer: List[dict] = []

        for record, csv in zip(
            self.parser.entries_json(), self.csvparser.entries_csv()
        ):

            result = orjson.loads(record)

            attributes = {}
            for attribute in result.get("attributes"):
                attributes[attribute.get("header").get("type_code")] = attribute
            result["attributes"] = attributes

            # entries_json method does not include the information of full path... :(
            if "FileName" in result["attributes"]:
                filepath = csv.decode("utf-8").split(",")[-1].strip()
                result["attributes"]["FileName"]["data"]["path"] = filepath

            for v in (
                "DATA",
                "BITMAP",
            ):
                for attribute in (
                    "vnc_first",
                    "vnc_last",
                ):
                    vnc = (
                        result.get("attributes", dict())
                        .get(v, dict())
                        .get("header", dict())
                        .get("residential_header", dict())
                        .get(attribute)
                    )
                    if vnc:
                        result["attributes"][v]["header"]["residential_header"][
                            attribute
                        ] = hex(vnc)

            buffer.append(result)

            if len(buffer) >= size:
                yield buffer
                buffer.clear()
        else:
            yield buffer


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


def mft2json(filepath: str) -> List[dict]:
    """Convert mft to json.

    Args:
        filepath (str): Input MFT file.

    Note:
        Since the content of the file is loaded into memory at once,
        it requires the same amount of memory as the file to be loaded.
    """
    r = Mft2es(filepath)

    buffer: List[dict] = sum(list(tqdm(r.gen_records(500))), list())
    return buffer


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


def console_mft2json():
    """ This function is loaded when used from the console.
    """

    # Args
    parser = argparse.ArgumentParser()
    parser.add_argument("mftfile", type=Path, help="Windows MFT file")
    parser.add_argument("jsonfile", type=Path, help="Output json file path")
    args = parser.parse_args()

    # Convert mft to json file.
    print(f"Converting {args.mftfile}")
    o = Path(args.jsonfile)
    o.write_text(orjson.dumps(mft2json(filepath=args.mftfile), option=orjson.OPT_INDENT_2).decode("utf-8"))
    print()

    print("Convert completed.")


if __name__ == "__main__":
    console_mft2es()
