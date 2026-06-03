# coding: utf-8
from hashlib import md5
from pathlib import Path

import pytest
from mft2es.views.Mft2esView import entry_point as m2e
from mft2es.views.Mft2jsonView import entry_point as m2j


# utils
def calc_md5(path: Path) -> str:
    if path.is_dir():
        return ""
    else:
        return md5(path.read_bytes()).hexdigest()


# command-line test cases
def test__mft2es_help(monkeypatch):
    argv = ["mft2es", "-h"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            m2e()
        assert exited.value.code == 0


def test__mft2es_version(monkeypatch):
    argv = ["mft2es", "-v"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            m2e()
        assert exited.value.code == 0


def test__mft2json_help(monkeypatch):
    argv = ["mft2json", "-h"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            m2j()
        assert exited.value.code == 0


def test__mft2json_version(monkeypatch):
    argv = ["mft2json", "-v"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            m2j()
        assert exited.value.code == 0


# behavior test cases
def test__mft2json_convert(monkeypatch):
    path = "tests/cache/MFT.json"
    argv = ["mft2json", "-o", path, "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert calc_md5(Path(path)) == "b3e228a56fd310dcbcb6ffc6e332cba9"


def test__mft2json_convert_multiprocessing(monkeypatch):
    path = "tests/cache/MFT-m.json"
    argv = ["mft2json", "-o", path, "-m", "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert calc_md5(Path(path)) == "b3e228a56fd310dcbcb6ffc6e332cba9"


def test__mft2json_timeline_convert(monkeypatch):
    path = "tests/cache/MFT-t.json"
    argv = ["mft2json", "--timeline", "-o", path, "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert calc_md5(Path(path)) == "cc18cc8cf067d68ca90084688ae44df0"


def test__mft2json_timeline_convert_multiprocessing(monkeypatch):
    path = "tests/cache/MFT-t-m.json"
    argv = ["mft2json", "--timeline", "-o", path, "-m", "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert calc_md5(Path(path)) == "cc18cc8cf067d68ca90084688ae44df0"


def test__mft2json_library_with_tags():
    from mft2es import mft2json

    records = mft2json("tests/cache/MFT", additional_tags=["host-1"])
    assert len(records) > 0
    for record in records:
        assert "host-1" in record.get("tags", [])


def test__mft2json_missing_file_exits_nonzero(monkeypatch):
    argv = ["mft2json", "/tmp/definitely-missing-mft"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            m2j()
    assert exited.value.code == 1


def test__mft2es_missing_file_exits_nonzero(monkeypatch):
    argv = ["mft2es", "/tmp/definitely-missing-mft"]
    with pytest.raises(SystemExit) as exited:
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            m2e()
    assert exited.value.code == 1


def test__mft2es_library_passes_verify_certs(monkeypatch):
    import mft2es as api

    captured = {}

    class DummyPresenter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def bulk_import(self):
            captured["called"] = True

    monkeypatch.setattr(api, "Mft2esPresenter", DummyPresenter)
    api.mft2es("tests/cache/MFT", verify_certs=False)

    assert captured["called"] is True
    assert captured["verify_certs"] is False


def test__mft2json_library_closes_mft(monkeypatch):
    import mft2es as api

    closed = False

    class DummyMft:
        def __init__(self, _path):
            pass

        def gen_timeline_records(self, **_kwargs):
            yield [{"tags": ["mft"]}]

        def close(self):
            nonlocal closed
            closed = True

    monkeypatch.setattr(api, "Mft2es", DummyMft)

    assert api.mft2json("dummy") == [{"tags": ["mft"]}]
    assert closed is True


def test__version_matches_cli_output(monkeypatch, capsys):
    from mft2es.__about__ import __version__

    argv = ["mft2es", "-v"]
    with pytest.raises(SystemExit):
        with monkeypatch.context() as m:
            m.setattr("sys.argv", argv)
            m2e()
    captured = capsys.readouterr()
    assert __version__ in (captured.out + captured.err)
