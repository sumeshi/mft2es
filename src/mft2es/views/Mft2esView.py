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

        self.parser.add_argument("--host", default="localhost", help="ElasticSearch host")
        self.parser.add_argument("--port", default=9200, help="ElasticSearch port number")
        self.parser.add_argument("--index", default="mft2es", help="Index name")
        self.parser.add_argument("--scheme", default="http", help="Scheme to use (http, https)")
        self.parser.add_argument("--pipeline", default="", help="Ingest pipeline to use")
        self.parser.add_argument("--login", default="", help="Login to use to connect to Elastic database")
        self.parser.add_argument("--pwd", default="", help="Password associated with the login")
    
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
        view = Mft2esView()
        mft_files = self.__list_mft_files(self.args.mft_files)

        if self.args.multiprocess:
            view.log(f"Multi-Process: {cpu_count()}", self.args.quiet)

        for mft_file in mft_files:
            view.log(f"Currently Importing {mft_file}.", self.args.quiet)

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
                logger=self.log
            ).bulk_import()

        view.log("Import completed.", self.args.quiet)


def entry_point():
    Mft2esView().run()


if __name__ == "__main__":
    entry_point()
