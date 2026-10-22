# coding: utf-8
from itertools import chain
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile
from typing import List, Optional, Union

import orjson
from tqdm import tqdm

from mft2es.models.Mft2es import Mft2es, PartialExtractionError, validate_chunk_size


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
        validate_chunk_size(chunk_size)
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

    def _check_output_path(self) -> None:
        if self.output_path.resolve() == self.input_path or (
            self.output_path.exists()
            and self.input_path.exists()
            and self.output_path.samefile(self.input_path)
        ):
            raise ValueError(
                "Input and output must be different files; "
                "they must not refer to the same file."
            )
        if self.output_path.is_symlink():
            raise ValueError("The output path must not be a symbolic link.")

    def export_json(self) -> None:
        self._check_output_path()
        r = Mft2es(self.input_path)
        records = None
        progress = None
        temporary_path = None
        record_count = 0
        try:
            records = r.gen_timeline_records(
                multiprocess=self.multiprocess,
                chunk_size=self.chunk_size,
                timeline_mode=self.timeline_mode,
                tags=self.tags,
            )
            progress = records if self.is_quiet else tqdm(records)
            with NamedTemporaryFile(
                mode="wb",
                dir=self.output_path.parent,
                prefix=f".{self.output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                if self.output_format == "json":
                    documents = list(chain.from_iterable(progress))
                    record_count = len(documents)
                    output.write(
                        orjson.dumps(
                            documents,
                            option=orjson.OPT_INDENT_2,
                        )
                    )
                else:
                    for chunk in progress:
                        for record in chunk:
                            output.write(orjson.dumps(record) + b"\n")
                            record_count += 1
                        output.flush()
            if r.diagnostics and record_count == 0:
                raise PartialExtractionError(r.diagnostics)
            self._check_output_path()
            if os.name == "posix" and self.output_path.exists():
                temporary_path.chmod(
                    stat.S_IMODE(self.output_path.stat().st_mode)
                )
            os.replace(temporary_path, self.output_path)
            if r.diagnostics:
                raise PartialExtractionError(r.diagnostics)
        finally:
            try:
                if progress is not None and progress is not records:
                    progress.close()
            finally:
                try:
                    if records is not None:
                        records.close()
                finally:
                    try:
                        r.close()
                    finally:
                        if temporary_path is not None:
                            temporary_path.unlink(missing_ok=True)
