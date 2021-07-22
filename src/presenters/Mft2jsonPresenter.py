# coding: utf-8
from pathlib import Path
from typing import List

import orjson
from tqdm import tqdm

from models.Mft2es import Mft2es


class Mft2jsonPresenter(object):

    def __init__(self, input_path: str, output_path: str, is_quiet: bool, multiprocess: bool, size: int):
        self.input_path = Path(input_path).resolve()
        self.output_path = output_path if output_path else Path(self.input_path).with_suffix('.json')
        self.is_quiet = is_quiet
        self.multiprocess = multiprocess
        self.size = size

    def mft2json(self) -> List[dict]:
        """Convert mft to json.

        Args:
            filepath (str): Input MFT file.

        Note:
            Since the content of the file is loaded into memory at once,
            it requires the same amount of memory as the file to be loaded.
        """
        r = Mft2es(self.input_path)
        generator = r.gen_records(self.multiprocess, self.size) if self.is_quiet else tqdm(r.gen_records(self.multiprocess, self.size))

        buffer: List[dict] = sum(generator, list())
        return buffer

    def export_json(self):
        self.output_path.write_text(
            orjson.dumps(self.mft2json(), option=orjson.OPT_INDENT_2).decode("utf-8")
        )
