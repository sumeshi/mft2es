# coding: utf-8
import traceback
from typing import List
from pathlib import Path

import orjson
from tqdm import tqdm

from mft2es.models.Mft2es import Mft2es
from mft2es.models.ElasticsearchUtils import ElasticsearchUtils


class Mft2esPresenter(object):

    def __init__(
        self,
        input_path: Path,
        host: str = "localhost",
        port: int = 9200,
        index: str = "mft2es",
        scheme: str = "http",
        pipeline: str = "",
        login: str = "",
        pwd: str = "",
        is_quiet: bool = False,
        multiprocess: bool = False,
        chunk_size: int = 500
    ):
        self.input_path = input_path
        self.host = host
        self.port = port
        self.index = index
        self.scheme = scheme
        self.pipeline = pipeline
        self.login = login
        self.pwd = pwd
        self.is_quiet = is_quiet
        self.multiprocess = multiprocess
        self.chunk_size = chunk_size

    def mft2es(self) -> List[dict]:
        r = Mft2es(self.input_path)
        generator = r.gen_records(self.multiprocess, self.chunk_size) if self.is_quiet else tqdm(r.gen_records(self.multiprocess, self.chunk_size))

        buffer: List[List[dict]] = generator
        return buffer

    def bulk_import(self):
        es = ElasticsearchUtils(
            hostname=self.host,
            port=self.port,
            scheme=self.scheme,
            login=self.login,
            pwd=self.pwd
        )

        for records in self.mft2es():
            try:
                es.bulk_indice(records, self.index, self.pipeline)
            except Exception:
                traceback.print_exc()
