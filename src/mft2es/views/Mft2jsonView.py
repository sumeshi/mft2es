# coding: utf-8
from multiprocessing import cpu_count

from mft2es.views.BaseView import BaseView
from mft2es.presenters.Mft2jsonPresenter import Mft2jsonPresenter


class Mft2jsonView(BaseView):

    def __init__(self):
        super().__init__()
        self.define_options()
        self.args = self.parser.parse_args()

    def define_options(self):
        self.parser.add_argument("mft_file", type=str, help="Windows MFT file to input.")
        self.parser.add_argument("--output-file", "-o", type=str, default="", help="json file path to output.")

    def run(self):
        view = Mft2jsonView()
        view.log(f"Converting {self.args.mft_file}.", self.args.quiet)

        if self.args.multiprocess:
            view.log(f"Multi-Process: {cpu_count()}", self.args.quiet)

        Mft2jsonPresenter(
            input_path=self.args.mft_file,
            output_path=self.args.output_file,
            is_quiet=self.args.quiet,
            multiprocess=self.args.multiprocess,
            chunk_size=self.args.size,
        ).export_json()

        view.log("Converted.", self.args.quiet)


def entry_point():
    Mft2jsonView().run()


if __name__ == "__main__":
    entry_point()
