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
        chunk_size: int = 500,
        logger=None
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
        self.logger = logger

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

        # Buffer for collecting results
        total_success = 0
        total_failed = []
        batch_count = 0

        for records in self.mft2es():
            try:
                success, failed = es.bulk_indice(records, self.index, self.pipeline)
                total_success += success
                if failed:
                    total_failed.extend(failed)
                batch_count += 1
                            
            except Exception:
                if self.logger:
                    self.logger("Error occurred during bulk indexing", self.is_quiet)
                traceback.print_exc()

        # Log summary results after tqdm completes
        if self.logger:
            self.logger(f"Bulk import completed: {batch_count} batches processed", self.is_quiet)
            self.logger(f"Successfully indexed: {total_success} documents", self.is_quiet)
            if total_failed:
                self.logger(f"Failed to index: {len(total_failed)} documents", self.is_quiet)
                for failure in total_failed[:3]:  # Show first 3 failures
                    self.logger(f"Error: {failure}", self.is_quiet)
