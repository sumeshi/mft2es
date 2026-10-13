import importlib
import os
import sys

import pytest


def test_es_cli_enumerates_directories_deduplicates_and_reports_partial_inputs(
    tmp_path, monkeypatch, capsys
):
    module = importlib.import_module("mft2es.views.Mft2esView")
    directory = tmp_path / "disk.evtx"
    directory.mkdir()
    nested = directory / "$MFT"
    nested.write_bytes(b"fixture")
    direct = tmp_path / "MFT"
    direct.write_bytes(b"fixture")
    wrong_extension = tmp_path / "unusual.txt"
    wrong_extension.write_bytes(b"fixture")
    empty = tmp_path / "empty"
    empty.mkdir()
    imported = []

    class Presenter:
        def __init__(self, input_path, **_kwargs):
            imported.append(input_path.resolve())

        def bulk_import(self):
            pass

    monkeypatch.setattr(module, "Mft2esPresenter", Presenter)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mft2es", "--quiet", str(direct), str(direct), str(wrong_extension),
            str(directory), str(tmp_path / "missing"), str(empty),
        ],
    )

    with pytest.raises(SystemExit) as exited:
        module.Mft2esView().run()

    assert exited.value.code == 1
    assert imported == [direct.resolve(), wrong_extension.resolve(), nested.resolve()]
    assert "skipping" in capsys.readouterr().err


def test_es_cli_skips_explicit_input_with_unreadable_metadata_and_continues(
    tmp_path, monkeypatch, capsys
):
    module = importlib.import_module("mft2es.views.Mft2esView")
    good_before = tmp_path / "before.mft"
    blocked = tmp_path / "blocked.mft"
    good_after = tmp_path / "after.mft"
    for path in (good_before, blocked, good_after):
        path.write_bytes(b"fixture")
    imported = []

    class Presenter:
        def __init__(self, input_path, **_kwargs):
            imported.append(input_path.resolve())

        def bulk_import(self):
            pass

    original_stat = module.Path.stat

    def stat(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError("permission denied")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(module.Path, "stat", stat)
    monkeypatch.setattr(module, "Mft2esPresenter", Presenter)
    monkeypatch.setattr(
        sys,
        "argv",
        ["mft2es", "--quiet", str(good_before), str(blocked), str(good_after)],
    )

    with pytest.raises(SystemExit) as exited:
        module.Mft2esView().run()

    assert exited.value.code == 1
    assert imported == [good_before.resolve(), good_after.resolve()]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(blocked) in captured.err
    assert "permission denied" in captured.err


@pytest.mark.skipif(
    os.name != "posix", reason="POSIX directory permissions required"
)
@pytest.mark.parametrize("mode", [0, 0o400])
def test_es_cli_reports_unreadable_subdirectory_and_keeps_readable_files(
    tmp_path, capsys, mode
):
    module = importlib.import_module("mft2es.views.Mft2esView")
    good = tmp_path / "MFT"
    good.write_bytes(b"fixture")
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    hidden = blocked / "$MFT"
    hidden.write_bytes(b"fixture")
    blocked.chmod(mode)
    try:
        if os.access(blocked, os.R_OK | os.X_OK):
            pytest.skip("process can bypass chmod restrictions")
        view = object.__new__(module.Mft2esView)
        files, had_invalid_input = view._Mft2esView__list_mft_files(
            [str(tmp_path)]
        )
        assert files == [good.resolve()]
        assert had_invalid_input
        error_output = capsys.readouterr().err
        assert str(blocked) in error_output or str(hidden) in error_output
        assert "no MFT file found" not in error_output
    finally:
        blocked.chmod(0o700)
