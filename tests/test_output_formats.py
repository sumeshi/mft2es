import importlib
import json
import os
import stat
import pytest

from mft2es.presenters.Mft2jsonPresenter import Mft2jsonPresenter


@pytest.mark.parametrize("output_format", ["jsonl", "ndjson"])
@pytest.mark.parametrize("quiet", [False, True])
def test_lines_stream_before_next_chunk(tmp_path, monkeypatch, output_format, quiet):
    output = tmp_path / "output.jsonl"
    closed = []

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_timeline_records(self, **kwargs):
            assert kwargs == dict(multiprocess=False, chunk_size=1,
                                  timeline_mode=True, tags=["host"])
            try:
                yield [{"name": "日本語", "tags": ["host"]}]
                staged = list(tmp_path.glob(f".{output.name}.*.tmp"))
                assert staged and staged[0].read_bytes().endswith(b"\n")
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


@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize("output_format", ["jsonl", "ndjson"])
def test_line_writer_failure_closes_generator_with_retained_traceback(
    tmp_path, monkeypatch, quiet, output_format
):
    module = importlib.import_module(Mft2jsonPresenter.__module__)
    closed = []

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_timeline_records(self, **kwargs):
            try:
                yield [{"n": 1}]
                yield [{"n": 2}]
            finally:
                closed.append("generator")

        def close(self):
            closed.append("parser")

    class Writer:
        name = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def write(self, data):
            raise OSError("output full")

    monkeypatch.setattr(module, "Mft2es", Parser)
    def fail_temp_file(**kwargs):
        temp_path = tmp_path / f"{kwargs['prefix']}test{kwargs['suffix']}"
        temp_path.touch()
        writer = Writer()
        writer.name = str(temp_path)
        return writer

    monkeypatch.setattr(module, "NamedTemporaryFile", fail_temp_file)
    presenter = Mft2jsonPresenter(
        tmp_path / "input.mft", tmp_path / "output.jsonl", is_quiet=quiet,
        output_format=output_format,
    )
    with pytest.raises(OSError) as raised:
        presenter.export_json()

    assert str(raised.value) == "output full"
    assert closed == ["generator", "parser"]
    assert list(tmp_path.glob(".*.tmp")) == []

@pytest.mark.parametrize("output_format", ["json", "jsonl"])
def test_quiet_cli_failure_preserves_existing_output_and_cleans_temp_file(
    tmp_path, monkeypatch, capsys, output_format
):
    module = importlib.import_module("mft2es.views.Mft2jsonView")
    source = tmp_path / "input.mft"
    output = tmp_path / "output.json"
    source.write_bytes(b"MFT")
    output.write_bytes(b"previous output")

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_timeline_records(self, **kwargs):
            yield [{"n": 1}]
            raise ValueError("parser broke")

        def close(self):
            pass

    monkeypatch.setattr(
        "mft2es.presenters.Mft2jsonPresenter.Mft2es", Parser
    )
    monkeypatch.setattr(
        "sys.argv",
        ["mft2json", "--quiet", "--format", output_format,
         str(source), "--output-file", str(output)],
    )
    with pytest.raises(SystemExit) as exited:
        module.Mft2jsonView().run()

    captured = capsys.readouterr()
    assert exited.value.code == 1
    assert captured.out == ""
    assert "parser broke" in captured.err
    assert "completed successfully" not in captured.out + captured.err
    assert output.read_bytes() == b"previous output"
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes only")
@pytest.mark.parametrize("output_format", ["json", "jsonl"])
def test_export_preserves_existing_output_mode(
    tmp_path, monkeypatch, output_format
):
    module = importlib.import_module("mft2es.presenters.Mft2jsonPresenter")
    source = tmp_path / "input.mft"
    output = tmp_path / "output.json"
    source.write_bytes(b"fixture")
    output.write_bytes(b"previous")
    output.chmod(0o664)

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_timeline_records(self, **kwargs):
            yield [{"record": 1}]

        def close(self):
            pass

    monkeypatch.setattr(module, "Mft2es", Parser)
    Mft2jsonPresenter(
        source, output, is_quiet=True, output_format=output_format
    ).export_json()

    assert stat.S_IMODE(output.stat().st_mode) == 0o664
