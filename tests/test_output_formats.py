import importlib
import json
import os
import stat

import orjson
import pytest

from mft2es.models.Mft2es import PartialExtractionError
from mft2es.presenters.Mft2jsonPresenter import Mft2jsonPresenter


@pytest.mark.parametrize("output_format", ["json", "jsonl", "ndjson"])
@pytest.mark.parametrize("quiet", [False, True])
def test_output_streams_before_next_chunk(tmp_path, monkeypatch, output_format, quiet):
    output = tmp_path / "output.json"
    closed = []
    first_record = {"name": "日本語", "tags": ["host"]}

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_timeline_records(self, **kwargs):
            assert kwargs == dict(multiprocess=False, chunk_size=1,
                                  timeline_mode=True, tags=["host"])
            try:
                yield [first_record]
                staged = list(tmp_path.glob(f".{output.name}.*.tmp"))
                assert staged
                expected = (
                    orjson.dumps([first_record], option=orjson.OPT_INDENT_2)[:-2]
                    if output_format == "json"
                    else orjson.dumps(first_record) + b"\n"
                )
                assert staged[0].read_bytes() == expected
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
    content = output.read_text(encoding="utf-8")
    actual = json.loads(content) if output_format == "json" else [
        json.loads(line) for line in content.splitlines()
    ]
    assert actual == [first_record, {"name": "second"}]
    assert "日本語" in output.read_text(encoding="utf-8")
    assert closed == ["generator", "parser"]
    assert Mft2jsonPresenter(
        tmp_path / "x.mft", "", output_format=output_format
    ).output_path.suffix == (".json" if output_format == "json" else ".jsonl")


@pytest.mark.parametrize(
    "chunks",
    [
        [],
        [[], []],
        [[{}]],
        [[], [{"name": "日本語", "path": "C:\\a\\b", "line": "one\ntwo"}], []],
        [
            [{"values": [None, True, False, -1, 1.5], "nested": {"empty": []}}],
            [],
            [{"second": [{"empty": {}}, ["a", "b"]]}, {"third": 3}],
        ],
    ],
    ids=["empty", "empty-chunks", "one-empty-object", "unicode", "nested-multiple"],
)
def test_streamed_json_matches_complete_array_bytes(tmp_path, monkeypatch, chunks):
    module = importlib.import_module(Mft2jsonPresenter.__module__)
    output = tmp_path / "output.json"

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_timeline_records(self, **kwargs):
            yield from chunks

        def close(self):
            pass

    monkeypatch.setattr(module, "Mft2es", Parser)
    Mft2jsonPresenter(tmp_path / "input", output, is_quiet=True).export_json()

    expected = orjson.dumps(
        [record for chunk in chunks for record in chunk],
        option=orjson.OPT_INDENT_2,
    )
    assert output.read_bytes() == expected
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


def test_streamed_json_serialization_failure_preserves_existing_output(
    tmp_path, monkeypatch
):
    module = importlib.import_module(Mft2jsonPresenter.__module__)
    output = tmp_path / "output.json"
    output.write_bytes(b"previous output")
    closed = []

    class Parser:
        diagnostics = []

        def __init__(self, path):
            pass

        def gen_timeline_records(self, **kwargs):
            try:
                yield [{"n": 1}]
                yield [{"unsupported": {1, 2}}]
                pytest.fail("continued after serialization failed")
            finally:
                closed.append("generator")

        def close(self):
            closed.append("parser")

    monkeypatch.setattr(module, "Mft2es", Parser)
    with pytest.raises(TypeError, match="not JSON serializable"):
        Mft2jsonPresenter(tmp_path / "input", output, is_quiet=True).export_json()

    assert output.read_bytes() == b"previous output"
    assert closed == ["generator", "parser"]
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


@pytest.mark.parametrize("has_valid_record", [False, True])
def test_streamed_json_partial_extraction_publishes_only_nonempty_output(
    tmp_path, monkeypatch, has_valid_record
):
    module = importlib.import_module(Mft2jsonPresenter.__module__)
    output = tmp_path / "output.json"
    output.write_bytes(b"previous output")
    diagnostics = [{"stage": "parse", "error": "bad record"}]
    closed = []

    class Parser:
        def __init__(self, path):
            self.diagnostics = diagnostics

        def gen_timeline_records(self, **kwargs):
            try:
                yield []
                if has_valid_record:
                    yield [{"n": 1}]
                yield []
            finally:
                closed.append("generator")

        def close(self):
            closed.append("parser")

    monkeypatch.setattr(module, "Mft2es", Parser)
    with pytest.raises(PartialExtractionError) as raised:
        Mft2jsonPresenter(tmp_path / "input", output, is_quiet=True).export_json()

    expected = (
        orjson.dumps([{"n": 1}], option=orjson.OPT_INDENT_2)
        if has_valid_record else b"previous output"
    )
    assert output.read_bytes() == expected
    assert raised.value.diagnostics == diagnostics
    assert closed == ["generator", "parser"]
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


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
@pytest.mark.parametrize("output_format", ["json", "jsonl", "ndjson"])
def test_writer_failure_closes_generator_with_retained_traceback(
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
