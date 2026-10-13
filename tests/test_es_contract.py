import importlib
from pathlib import Path
from unittest.mock import MagicMock
import pytest

@pytest.mark.parametrize("failure", ["partial", "transport"])
def test_bulk_failures_propagate_and_close(monkeypatch, failure):
    module = importlib.import_module("mft2es.presenters.Mft2esPresenter")
    presenter = module.Mft2esPresenter(Path("input"), is_quiet=True)
    state = []
    def chunks():
        try:
            yield [{"id": 1}]
            pytest.fail("continued after failed batch")
        finally:
            state.append("closed")
    monkeypatch.setattr(presenter, "mft2es", chunks)
    client = MagicMock()
    if failure == "partial":
        client.bulk_indice.return_value = (0, [{"error": "rejected"}])
    else:
        client.bulk_indice.side_effect = RuntimeError("transport failed")
    monkeypatch.setattr(module, "ElasticsearchUtils", lambda **kwargs: client)
    with pytest.raises(RuntimeError):
        presenter.bulk_import()
    client.close.assert_called_once()
    assert state == ["closed"]


@pytest.mark.parametrize("quiet", [False, True])
def test_bulk_failure_closes_progress_raw_generator_then_parser(
    monkeypatch, quiet
):
    module = importlib.import_module("mft2es.presenters.Mft2esPresenter")
    state = []

    class Parser:
        def __init__(self, path):
            pass

        def gen_timeline_records(self, **kwargs):
            try:
                yield [{"id": 1}]
                pytest.fail("continued after failed batch")
            finally:
                state.append("generator")

        def close(self):
            state.append("parser")

    class Progress:
        def __init__(self, records):
            self.records = records

        def __iter__(self):
            return iter(self.records)

        def close(self):
            state.append("progress")

    client = MagicMock()
    client.bulk_indice.side_effect = RuntimeError("transport failed")
    monkeypatch.setattr(module, "Mft2es", Parser)
    monkeypatch.setattr(module, "tqdm", Progress)
    monkeypatch.setattr(module, "ElasticsearchUtils", lambda **kwargs: client)

    with pytest.raises(RuntimeError) as error:
        module.Mft2esPresenter(Path("input"), is_quiet=quiet).bulk_import()

    assert str(error.value) == "transport failed"
    assert state.count("generator") == 1
    assert state.count("progress") == (0 if quiet else 1)
    assert state.count("parser") == 1
    assert state[-1] == "parser"
    client.close.assert_called_once()


def test_cli_passes_tls_options(tmp_path, monkeypatch):
    module = importlib.import_module("mft2es.views.Mft2esView")
    source = tmp_path / "MFT"
    source.write_bytes(b"regf" + b"\0" * 4096)
    client = MagicMock()
    monkeypatch.setattr(module, "Mft2esPresenter", client)
    monkeypatch.setattr("sys.argv", ["mft2es", str(source), "--ca-certs", "ca.pem", "--no-verify-certs"])
    module.Mft2esView().run()
    assert client.call_args.kwargs["ca_certs"] == "ca.pem"
    assert client.call_args.kwargs["verify_certs"] is False

def test_cli_processes_good_bad_good_inputs_then_exits_partial(
    tmp_path, monkeypatch, capsys
):
    module = importlib.import_module("mft2es.views.Mft2esView")
    paths = [tmp_path / name for name in ("good1", "bad", "good2")]
    for path in paths:
        path.write_bytes(b"MFT")
    attempted = []

    class Presenter:
        def __init__(self, input_path, **_kwargs):
            self.input_path = input_path

        def bulk_import(self):
            attempted.append(self.input_path)
            if self.input_path == paths[1]:
                raise module.InputProcessingError("bad input")

    monkeypatch.setattr(module, "Mft2esPresenter", Presenter)
    monkeypatch.setattr(
        "sys.argv", ["mft2es", "--quiet", *(str(path) for path in paths)]
    )
    with pytest.raises(SystemExit) as exited:
        module.Mft2esView().run()

    captured = capsys.readouterr()
    assert exited.value.code == 1
    assert attempted == paths
    assert captured.out == ""
    assert "bad input" in captured.err

def test_cli_does_not_continue_after_elasticsearch_failure(
    tmp_path, monkeypatch
):
    module = importlib.import_module("mft2es.views.Mft2esView")
    paths = [tmp_path / name for name in ("first", "later")]
    for path in paths:
        path.write_bytes(b"MFT")
    attempted = []

    class Presenter:
        def __init__(self, input_path, **_kwargs):
            self.input_path = input_path

        def bulk_import(self):
            attempted.append(self.input_path)
            raise RuntimeError("Elasticsearch unavailable")

    monkeypatch.setattr(module, "Mft2esPresenter", Presenter)
    monkeypatch.setattr("sys.argv", ["mft2es", "--quiet", *(str(p) for p in paths)])
    with pytest.raises(RuntimeError, match="Elasticsearch unavailable"):
        module.Mft2esView().run()
    assert attempted == paths[:1]

def test_tls_options(monkeypatch):
    module = importlib.import_module("mft2es.models.ElasticsearchUtils")
    client = MagicMock()
    monkeypatch.setattr(module, "Elasticsearch", client)
    module.ElasticsearchUtils("localhost", 9200, "https", "user", "", ca_certs="ca.pem")
    assert client.call_args.kwargs["verify_certs"] is True
    assert client.call_args.kwargs["ca_certs"] == "ca.pem"
    assert client.call_args.kwargs["basic_auth"] == ("user", "")
