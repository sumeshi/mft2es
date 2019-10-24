# coding: utf-8
import json
import codecs
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

    def bulk_indice(self, records, index_name: str, type_name: str) -> None:
        bulk(self.es, [
            {
                '_index': index_name,
                '_type': type_name,
                '_source': record
            } for record in records]
        )


class Mft2es(object):
    def __init__(self, filepath: str) -> None:
        self.path = Path(filepath)
        self.parser = PyMftParser(self.path.open(mode='rb'))

    def gen_json(self, size: int) -> Generator:
        buffer: List[dict] = []

        for record in self.parser.entries_json():
            result = json.loads(record)
            buffer.append(result)

            if len(buffer) >= size:
                yield buffer
                buffer.clear()
        else:
            yield buffer


def mft2es(filepath: str, host: str = 'localhost', port: int = 9200, index: str = 'mft2es', type: str = 'mft2es', size: int = 500):
    es = ElasticsearchUtils(hostname=host, port=port)
    r = Mft2es(filepath)

    for records in tqdm(r.gen_json(size)):
        try:
            es.bulk_indice(records, index, type)
        except Exception:
            traceback.print_exc()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mftfile', help='Windows Master File Table')
    parser.add_argument('--host', default='localhost', help='ElasticSearch host address')
    parser.add_argument('--port', default=9200, help='ElasticSearch port number')
    parser.add_argument('--index', default='mft2es', help='Index name')
    parser.add_argument('--type', default='mft2es', help='Document type name')
    parser.add_argument('--size', default=500, help='Bulk insert buffer size')
    args = parser.parse_args()

    mft2es(
        filepath=args.mftfile,
        host=args.host,
        port=int(args.port),
        index=args.index,
        type=args.type,
        size=int(args.size)
    )


if __name__ == '__main__':
    main()
