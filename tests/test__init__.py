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
