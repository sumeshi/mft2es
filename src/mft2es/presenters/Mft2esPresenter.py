# coding: utf-8
from pathlib import Path
from typing import List, Optional, Union

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
        logger=None,
        timeline_mode: bool = False,
        tags: Optional[Union[str, List[str]]] = None,
        verify_certs: bool = True,
        ca_certs: str | None = None,
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
        self.timeline_mode = timeline_mode
        self.tags = tags
        self.verify_certs = verify_certs
        self.ca_certs = ca_certs

    def mft2es(self):
        mft2es_instance = Mft2es(self.input_path)
        try:
            generator = mft2es_instance.gen_timeline_records(
                multiprocess=self.multiprocess,
                chunk_size=self.chunk_size,
                timeline_mode=self.timeline_mode,
                tags=self.tags,
            )
            if not self.is_quiet:
                generator = tqdm(generator)
            yield from generator
        finally:
            mft2es_instance.close()

    def bulk_import(self):
        es = ElasticsearchUtils(
            hostname=self.host, port=self.port, scheme=self.scheme,
            login=self.login, pwd=self.pwd, verify_certs=self.verify_certs,
            ca_certs=self.ca_certs,
        )
        chunks = None
        total_success = 0
        batch_count = 0
        try:
            chunks = self.mft2es()
            for records in chunks:
                success, failed = es.bulk_indice(records, self.index, self.pipeline)
                total_success += success
                batch_count += 1
                if failed:
                    raise RuntimeError(
                        f"Elasticsearch failed to index {len(failed)} document(s)"
                    )
        finally:
            try:
                close = getattr(chunks, "close", None)
                if close is not None:
                    close()
            finally:
                es.close()
        if self.logger:
            self.logger(
                f"Bulk import completed: {batch_count} batches processed",
                self.is_quiet,
            )
            self.logger(f"Successfully indexed: {total_success} documents", self.is_quiet)
