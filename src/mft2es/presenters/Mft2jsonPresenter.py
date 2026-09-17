# coding: utf-8
from itertools import chain
from pathlib import Path
from typing import List, Optional, Union

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
        chunk_size: int = 500,
        timeline_mode: bool = False,
        tags: Optional[Union[str, List[str]]] = None,
        output_format: str = "json",
    ):
        if output_format not in ("json", "jsonl", "ndjson"):
            raise ValueError(f"Invalid output format: {output_format}")
        self.output_format = output_format
        self.input_path = Path(input_path).resolve()
        self.output_path: Path = (
            Path(output_path)
            if output_path
            else Path(self.input_path).with_suffix(
                ".json" if output_format == "json" else ".jsonl"
            )
        )
        self.is_quiet = is_quiet
        self.multiprocess = multiprocess
        self.chunk_size = chunk_size
        self.timeline_mode = timeline_mode
        self.tags = tags

    def export_json(self) -> None:
        if self.output_path.resolve() == self.input_path or (
            self.output_path.exists() and self.input_path.exists()
            and self.output_path.samefile(self.input_path)
        ):
            raise ValueError(
                "Input and output must be different files; "
                "they must not refer to the same file."
            )
        if self.output_path.is_symlink():
            raise ValueError("The output path must not be a symbolic link.")
        r = Mft2es(self.input_path)
        try:
            generator = (
                r.gen_timeline_records(
                    multiprocess=self.multiprocess,
                    chunk_size=self.chunk_size,
                    timeline_mode=self.timeline_mode,
                    tags=self.tags,
                )
                if self.is_quiet
                else tqdm(
                    r.gen_timeline_records(
                        multiprocess=self.multiprocess,
                        chunk_size=self.chunk_size,
                        timeline_mode=self.timeline_mode,
                        tags=self.tags,
                    )
                )
            )
            if self.output_format == "json":
                self.output_path.write_bytes(
                    orjson.dumps(
                        list(chain.from_iterable(generator)), option=orjson.OPT_INDENT_2
                    )
                )
            else:
                with self.output_path.open("wb") as output:
                    for chunk in generator:
                        for record in chunk:
                            output.write(orjson.dumps(record) + b"\n")
                        output.flush()
        finally:
            r.close()
