import importlib
import json

import pytest

from mft2es.presenters.Mft2jsonPresenter import Mft2jsonPresenter


@pytest.mark.parametrize("output_format", ["jsonl", "ndjson"])
@pytest.mark.parametrize("quiet", [False, True])
def test_lines_stream_before_next_chunk(tmp_path, monkeypatch, output_format, quiet):
    output = tmp_path / "output.jsonl"
    closed = []

    class Parser:
        def __init__(self, path):
            pass

        def gen_timeline_records(self, **kwargs):
            assert kwargs == dict(multiprocess=False, chunk_size=1,
                                  timeline_mode=True, tags=["host"])
            try:
                yield [{"name": "日本語", "tags": ["host"]}]
                assert output.read_bytes().endswith(b"\n")
                yield [{"name": "second"}]
            finally:
                closed.append("generator")

        def close(self):
            closed.append("parser")

    module = importlib.import_module(Mft2jsonPresenter.__module__)
    monkeypatch.setattr(module, "Mft2es", Parser)
    Mft2jsonPresenter(tmp_path / "input", output, is_quiet=quiet, chunk_size=1,
                      timeline_mode=True, tags=["host"],
                      output_format=output_format).export_json()
    assert [json.loads(line) for line in output.read_text().splitlines()] == [
        {"name": "日本語", "tags": ["host"]}, {"name": "second"}]
    assert "日本語" in output.read_text(encoding="utf-8")
    assert closed == ["generator", "parser"]
    assert Mft2jsonPresenter(tmp_path / "x.mft", "", output_format=output_format).output_path.suffix == ".jsonl"


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink", "default"])
@pytest.mark.parametrize("output_format", ["json", "jsonl", "ndjson"])
def test_rejects_input_output_alias_before_parser(tmp_path, monkeypatch, alias, output_format):
    source = tmp_path / ("input.json" if output_format == "json" else "input.jsonl")
    source.write_bytes(b"evidence")
    destination = tmp_path / "alias"
    if alias == "symlink":
        destination.symlink_to(source)
    elif alias == "hardlink":
        destination.hardlink_to(source)
    else:
        destination = source if alias == "same" else ""
    module = importlib.import_module(Mft2jsonPresenter.__module__)
    monkeypatch.setattr(module, "Mft2es", lambda path: pytest.fail("parser opened"))
    with pytest.raises(ValueError, match="same"):
        Mft2jsonPresenter(source, destination, output_format=output_format).export_json()
    assert source.read_bytes() == b"evidence"


def test_jsonl_default_suffix(tmp_path):
    presenter = Mft2jsonPresenter(tmp_path / "input.mft", "", output_format="jsonl")
    assert presenter.output_path == tmp_path / "input.jsonl"
