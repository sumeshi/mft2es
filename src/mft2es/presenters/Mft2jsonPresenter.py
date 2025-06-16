# coding: utf-8
from itertools import chain
from pathlib import Path
from typing import List

import orjson
from tqdm import tqdm

from mft2es.models.Mft2es import Mft2es


class Mft2jsonPresenter(object):

    def __init__(
        self,
        input_path: str,
        output_path: str,
        is_quiet: bool = False,
        multiprocess: bool = False,
        chunk_size: int = 500
    ):
        self.input_path = Path(input_path).resolve()
        self.output_path: Path = (
            Path(output_path)
            if output_path
            else Path(self.input_path).with_suffix('.json')
        )
        self.is_quiet = is_quiet
        self.multiprocess = multiprocess
        self.chunk_size = chunk_size

    def mft2json(self) -> List[dict]:
        r = Mft2es(self.input_path)
        generator = r.gen_records(self.multiprocess, self.chunk_size) if self.is_quiet else tqdm(r.gen_records(self.multiprocess, self.chunk_size))

        buffer: List[dict] = list(chain.from_iterable(generator))
        return buffer

    def export_json(self):
        self.output_path.write_text(
            orjson.dumps(self.mft2json(), option=orjson.OPT_INDENT_2).decode("utf-8")
        )
