# coding: utf-8
from typing import List
from pathlib import Path
from multiprocessing import cpu_count

from mft2es.views.BaseView import BaseView
from mft2es.presenters.Mft2esPresenter import Mft2esPresenter


class Mft2esView(BaseView):

    def __init__(self):
        super().__init__()
        self.define_options()
        self.args = self.parser.parse_args()

    def define_options(self):
        self.parser.add_argument(
            "mft_files",
            nargs="+",
            type=str,
            help="Windows MFT or directories containing them. (filename must be set 'MFT', or '$MFT')",
        )

        self.parser.add_argument(
            "--host", default="localhost", help="ElasticSearch host"
        )
        self.parser.add_argument(
            "--port", default=9200, help="ElasticSearch port number"
        )
        self.parser.add_argument("--index", default="mft2es", help="Index name")
        self.parser.add_argument(
            "--scheme", default="http", help="Scheme to use (http, https)"
        )
        self.parser.add_argument(
            "--pipeline", default="", help="Ingest pipeline to use"
        )
        self.parser.add_argument(
            "--login", default="", help="Login to use to connect to Elastic database"
        )
        self.parser.add_argument(
            "--pwd", default="", help="Password associated with the login"
        )
        self.parser.add_argument(
            "--timeline",
            action="store_true",
            help="Enable timeline analysis mode (separates records by type)",
        )
        self.parser.add_argument(
            "--no-verify-certs",
            action="store_true",
            help="Disable SSL/TLS certificate verification",
        )

    def __list_mft_files(self, mft_files: List[str]) -> List[Path]:
        mft_path_list = list()
        for mft_file in mft_files:
            if Path(mft_file).is_dir():
                mft_path_list.extend(Path(mft_file).glob("**/mft"))
                mft_path_list.extend(Path(mft_file).glob("**/MFT"))
                mft_path_list.extend(Path(mft_file).glob("**/$MFT"))
            else:
                mft_path_list.append(Path(mft_file))

        return mft_path_list

    def run(self):
        mft_files = self.__list_mft_files(self.args.mft_files)
        processed_count = 0
        had_invalid_input = False

        if self.args.multiprocess:
            self.log(f"Multi-Process: {cpu_count()}", self.args.quiet)

        if self.args.timeline:
            self.log("Timeline analysis mode enabled", self.args.quiet)

        if not mft_files:
            self.log("Error: no MFT files found.", self.args.quiet)
            raise SystemExit(1)

        for mft_file in mft_files:
            if not mft_file.exists():
                self.log(
                    f"Warning: {mft_file} does not exist, skipping.", self.args.quiet
                )
                had_invalid_input = True
                continue
            if not mft_file.is_file():
                self.log(
                    f"Warning: {mft_file} is not a file, skipping.", self.args.quiet
                )
                had_invalid_input = True
                continue
            self.log(f"Currently Importing {mft_file}.", self.args.quiet)

            Mft2esPresenter(
                input_path=mft_file,
                host=self.args.host,
                port=int(self.args.port),
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
            processed_count += 1

        if processed_count == 0:
            self.log("Error: no valid MFT files were imported.", self.args.quiet)
            raise SystemExit(1)

        if had_invalid_input:
            self.log("Import completed with skipped inputs.", self.args.quiet)
            raise SystemExit(1)

        self.log("Import completed.", self.args.quiet)


def entry_point():
    BaseView.run_entry_point(Mft2esView)


if __name__ == "__main__":
    entry_point()
