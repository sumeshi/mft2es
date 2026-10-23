"""Timeline defaults and the explicit Standard compatibility path."""

import importlib
import json

import pytest

import mft2es as api
from mft2es.presenters.Mft2esPresenter import Mft2esPresenter
from mft2es.presenters.Mft2jsonPresenter import Mft2jsonPresenter
from test_native_csv_contract import synthetic_file_record


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "MFT"
    path.write_bytes(synthetic_file_record(0, "sample.txt"))
    return path


@pytest.mark.parametrize(
    "options,timeline",
    [({}, True), ({"timeline_mode": True}, True), ({"timeline_mode": False}, False)],
)
def test_public_json_api_defaults_to_timeline_and_keeps_standard(
    source, options, timeline
):
    records = api.mft2json(str(source), **options)
    assert len(records) == (4 if timeline else 1)
    assert all(("windows" in record) is timeline for record in records)
    if not timeline:
        assert records[0]["attributes"]["FileName"]["data"]["path"].endswith(
            "sample.txt"
        )


@pytest.mark.parametrize(
    "options,timeline",
    [({}, True), ({"timeline_mode": True}, True), ({"timeline_mode": False}, False)],
)
def test_public_es_api_passes_default_and_explicit_mode(monkeypatch, options, timeline):
    captured = {}

    class Presenter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def bulk_import(self):
            pass

    monkeypatch.setattr(api, "Mft2esPresenter", Presenter)
    api.mft2es("MFT", **options)
    assert captured["timeline_mode"] is timeline


@pytest.mark.parametrize("view_name", ["Mft2esView", "Mft2jsonView"])
@pytest.mark.parametrize(
    "flags,timeline", [([], True), (["--timeline"], True), (["--no-timeline"], False)]
)
def test_cli_forwards_default_and_explicit_mode(
    source, monkeypatch, view_name, flags, timeline
):
    module = importlib.import_module("mft2es.views." + view_name)
    captured = {}

    class Presenter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def bulk_import(self):
            pass

        export_json = bulk_import

    monkeypatch.setattr(module, view_name.replace("View", "Presenter"), Presenter)
    monkeypatch.setattr("sys.argv", [view_name, str(source), "--quiet", *flags])
    getattr(module, view_name)().run()
    assert captured["timeline_mode"] is timeline


@pytest.mark.parametrize(
    "options,timeline", [({}, True), ({"timeline_mode": False}, False)]
)
def test_direct_presenters_match_default_and_standard(
    source, tmp_path, options, timeline
):
    expected = api.mft2json(str(source), **options)
    producer = Mft2esPresenter(source, is_quiet=True, **options)
    assert [record for chunk in producer.mft2es() for record in chunk] == expected
    output = tmp_path / "records.json"
    Mft2jsonPresenter(source, output, is_quiet=True, **options).export_json()
    assert json.loads(output.read_bytes()) == expected
    assert len(expected) == (4 if timeline else 1)
