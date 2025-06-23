# coding: utf-8
from hashlib import md5
from pathlib import Path

import pytest
from mft2es.views.Mft2esView import entry_point as m2e
from mft2es.views.Mft2jsonView import entry_point as m2j

# utils
def calc_md5(path: Path) -> str:
    if path.is_dir():
        return ''
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
    path = 'tests/cache/MFT.json'
    argv = ["mft2json", "-o", path, "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert calc_md5(Path(path)) == "b3e228a56fd310dcbcb6ffc6e332cba9"

def test__mft2json_convert_multiprocessing(monkeypatch):
    path = 'tests/cache/MFT-m.json'
    argv = ["mft2json", "-o", path, "-m", "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert calc_md5(Path(path)) == "b3e228a56fd310dcbcb6ffc6e332cba9"

def test__mft2json_timeline_convert(monkeypatch):
    path = 'tests/cache/MFT-t.json'
    argv = ["mft2json", "--timeline", "-o", path, "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert calc_md5(Path(path)) == "cc18cc8cf067d68ca90084688ae44df0"

def test__mft2json_timeline_convert_multiprocessing(monkeypatch):
    path = 'tests/cache/MFT-t-m.json'
    argv = ["mft2json", "--timeline", "-o", path, "-m", "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert calc_md5(Path(path)) == "cc18cc8cf067d68ca90084688ae44df0"
