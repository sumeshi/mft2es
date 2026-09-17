# coding: utf-8
from multiprocessing import cpu_count
from pathlib import Path

from mft2es.views.BaseView import BaseView
from mft2es.presenters.Mft2jsonPresenter import Mft2jsonPresenter


class Mft2jsonView(BaseView):

    def __init__(self):
        super().__init__()
        self.define_options()
        self.args = self.parser.parse_args()

    def define_options(self):
        self.parser.add_argument(
            "--format", choices=("json", "jsonl", "ndjson"), default="json",
            help=(
                "Output format (default: json). "
                "JSONL/NDJSON writes one record per line."
            ),
        )
        self.parser.add_argument(
            "mft_file", type=str, help="Input MFT file."
        )
        self.parser.add_argument(
            "--output-file",
            "-o",
            type=str,
            default="",
            help="Output file path.",
        )
        self.parser.add_argument(
            "--timeline",
            action="store_true",
            help="Enable timeline analysis mode (separate records by type).",
        )

    def run(self):
        mft_path = Path(self.args.mft_file)
        if not mft_path.exists():
            self.log(f"Error: input path does not exist: {mft_path}", self.args.quiet)
            raise SystemExit(1)
        if not mft_path.is_file():
            self.log(f"Error: input path is not a regular file: {mft_path}", self.args.quiet)
            raise SystemExit(1)

        self.log(f"Converting {self.args.mft_file}.", self.args.quiet)

        if self.args.multiprocess:
            self.log(f"Multiprocessing enabled ({cpu_count()} workers).", self.args.quiet)

        if self.args.timeline:
            self.log("Timeline analysis mode enabled", self.args.quiet)

        Mft2jsonPresenter(
            input_path=self.args.mft_file,
            output_path=self.args.output_file,
            is_quiet=self.args.quiet,
            multiprocess=self.args.multiprocess,
            chunk_size=self.args.size,
            timeline_mode=self.args.timeline,
            tags=self.args.tags,
            output_format=self.args.format,
        ).export_json()

        self.log("Conversion completed successfully.", self.args.quiet)


def entry_point():
    BaseView.run_entry_point(Mft2jsonView)


if __name__ == "__main__":
    entry_point()
