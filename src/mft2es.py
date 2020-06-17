# coding: utf-8
import json
import argparse
import traceback

from pathlib import Path
from typing import List, Generator

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from mft import PyMftParser
from tqdm import tqdm


class ElasticsearchUtils(object):
    def __init__(self, hostname: str, port: int) -> None:
        self.es = Elasticsearch(host=hostname, port=port)

    def bulk_indice(self, records, index_name: str) -> None:
        bulk(
            self.es, [{"_index": index_name, "_source": record} for record in records],
        )


class Mft2es(object):
    def __init__(self, filepath: str) -> None:
        self.path = Path(filepath)
        self.parser = PyMftParser(self.path.open(mode="rb"))
        self.csvparser = PyMftParser(self.path.open(mode="rb"))

    def gen_json(self, size: int) -> Generator:
        buffer: List[dict] = []

        for record, csv in zip(
            self.parser.entries_json(), self.csvparser.entries_csv()
        ):

            result = json.loads(record)

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
):
    es = ElasticsearchUtils(hostname=host, port=port)
    r = Mft2es(filepath)

    for records in tqdm(r.gen_json(size)):
        try:
            es.bulk_indice(records, index)
        except Exception:
            traceback.print_exc()


def console_mft2es():
    parser = argparse.ArgumentParser()
    parser.add_argument("mftfile", help="Windows Master File Table")
    parser.add_argument(
        "--host", default="localhost", help="ElasticSearch host address"
    )
    parser.add_argument("--port", default=9200, help="ElasticSearch port number")
    parser.add_argument("--index", default="mft2es", help="Index name")
    parser.add_argument("--size", default=500, help="Bulk insert buffer size")
    args = parser.parse_args()

    mft2es(
        filepath=args.mftfile,
        host=args.host,
        port=int(args.port),
        index=args.index,
        size=int(args.size),
    )


if __name__ == "__main__":
    console_mft2es()
