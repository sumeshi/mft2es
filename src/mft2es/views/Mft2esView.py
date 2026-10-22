# coding: utf-8
from typing import List
import os
from pathlib import Path
from multiprocessing import cpu_count
import stat
import sys

from mft2es.views.BaseView import BaseView
from mft2es.models.Mft2es import PartialExtractionError
from mft2es.presenters.Mft2esPresenter import Mft2esPresenter
from mft2es.presenters.Mft2esPresenter import InputProcessingError


class Mft2esView(BaseView):

    def __init__(self):
        super().__init__()
        self.define_options()
        self.args = self.parser.parse_args()

    def define_options(self):
        self.parser.add_argument(
            "--ca-certs",
            default=None,
            help="Path to a CA certificate bundle for TLS verification.",
        )
        self.parser.add_argument(
            "mft_files",
            nargs="+",
            type=str,
            help=(
                "Input MFT files or directories. Files are identified by the "
                "names MFT or $MFT."
            ),
        )

        self.parser.add_argument(
            "--host", default="localhost", help="Elasticsearch host."
        )
        self.parser.add_argument(
            "--port", default=9200, type=int, help="Elasticsearch port."
        )
        self.parser.add_argument("--index", default="mft2es", help="Elasticsearch index name.")
        self.parser.add_argument(
            "--scheme", default="http", help="Connection scheme (http or https)."
        )
        self.parser.add_argument(
            "--pipeline", default="", help="Elasticsearch ingest pipeline to use."
        )
        self.parser.add_argument(
            "--login",
            default="",
            help="Username for Elasticsearch authentication.",
        )
        self.parser.add_argument(
            "--pwd",
            default="",
            help="Password for Elasticsearch authentication.",
        )
        self.parser.add_argument(
            "--timeline",
            action="store_true",
            help="Enable timeline analysis mode (separate records by type).",
        )
        self.parser.add_argument(
            "--no-verify-certs",
            action="store_true",
            help="Disable TLS certificate verification.",
        )

    def __list_mft_files(self, mft_files: List[str]):
        mft_path_list = list()
        had_invalid_input = False
        for mft_file in mft_files:
            path = Path(mft_file)
            try:
                mode = path.stat().st_mode
            except OSError as error:
                print(
                    f"Warning: could not read {mft_file}: {error}; skipping.",
                    file=sys.stderr,
                )
                had_invalid_input = True
                continue

            if stat.S_ISDIR(mode):
                names = ("mft", "MFT", "$MFT")
                found_by_name = {name: [] for name in names}
                walk_had_error = False

                def onerror(error):
                    nonlocal had_invalid_input
                    nonlocal walk_had_error
                    print(
                        "Warning: could not read "
                        f"{error.filename or mft_file}: {error}; skipping.",
                        file=sys.stderr,
                    )
                    had_invalid_input = True
                    walk_had_error = True

                for root, _, filenames in os.walk(
                    path, onerror=onerror, followlinks=False
                ):
                    for filename in filenames:
                        for name in names:
                            if os.path.normcase(filename) != os.path.normcase(name):
                                continue
                            candidate = Path(root) / filename
                            try:
                                if stat.S_ISREG(candidate.stat().st_mode):
                                    found_by_name[name].append(candidate)
                            except OSError as error:
                                onerror(error)
                            break
                found = [candidate for name in names for candidate in found_by_name[name]]
                if not found and not walk_had_error:
                    print(f"Warning: no MFT file found under {mft_file}; skipping.", file=sys.stderr)
                    had_invalid_input = True
                mft_path_list.extend(found)
            elif stat.S_ISREG(mode):
                mft_path_list.append(path)
            else:
                print(f"Warning: {mft_file} is not a regular file; skipping.", file=sys.stderr)
                had_invalid_input = True

        unique_paths = []
        seen_paths = set()
        for path in mft_path_list:
            try:
                resolved = path.resolve()
            except OSError as error:
                print(
                    f"Warning: could not read {path}: {error}; skipping.",
                    file=sys.stderr,
                )
                had_invalid_input = True
                continue
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                unique_paths.append(resolved)
        return unique_paths, had_invalid_input

    def run(self):
        mft_files, had_invalid_input = self.__list_mft_files(self.args.mft_files)

        if self.args.multiprocess:
            self.log(f"Multiprocessing enabled ({cpu_count()} workers).", self.args.quiet)

        if self.args.timeline:
            self.log("Timeline analysis mode enabled", self.args.quiet)

        if not mft_files:
            print("Error: no MFT files found.", file=sys.stderr)
            raise SystemExit(1)

        for mft_file in mft_files:
            self.log(f"Importing {mft_file}...", self.args.quiet)

            try:
                Mft2esPresenter(
                    input_path=mft_file,
                    host=self.args.host,
                    ca_certs=self.args.ca_certs,
                    port=self.args.port,
                    index=self.args.index,
                    scheme=self.args.scheme,
                    pipeline=self.args.pipeline,
                    login=self.args.login,
                    pwd=self.args.pwd,
                    is_quiet=self.args.quiet,
                    multiprocess=self.args.multiprocess,
                    chunk_size=int(self.args.size),
                    logger=self.log,
                    timeline_mode=self.args.timeline,
                    tags=self.args.tags,
                    verify_certs=not self.args.no_verify_certs,
                ).bulk_import()
            except (InputProcessingError, PartialExtractionError) as error:
                print(f"Warning: failed to process {mft_file}: {error}", file=sys.stderr)
                had_invalid_input = True
                continue
        if had_invalid_input:
            print("Import completed with input failures.", file=sys.stderr)
            raise SystemExit(1)

        self.log("Import completed successfully.", self.args.quiet)


def entry_point():
    BaseView.run_entry_point(Mft2esView)


if __name__ == "__main__":
    entry_point()
