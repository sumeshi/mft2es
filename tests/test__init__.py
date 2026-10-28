# coding: utf-8
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest
from mft2es.views.Mft2esView import entry_point as m2e
from mft2es.views.Mft2jsonView import entry_point as m2j

# Fixed sample, mft 0.7.0: all Standard attributes and unchanged Timeline fields.
STANDARD_DIGEST = "4c79d805ae5d97d3613922b28c84e73fa8ce1f740fff3845eb6ee0573ea3b363"
TIMELINE_DIGEST = "489ce05ab060b3f20822fb57176a13fe6093dce975f87bc1a5f902d840637d75"


def canonical_digest(records: list[dict], *, timeline: bool = False) -> str:
    """Check every field and record order without host paths or JSON key order."""
    checksum = sha256()
    for original in records:
        record = deepcopy(original)
        if timeline:
            assert record["log"]["file"]["path"] == str(
                Path("tests/cache/MFT").resolve()
            )
            record["log"]["file"]["path"] = "MFT"
            entry = record["windows"]["mft"]["record"]
            entry["path"] = entry["path"].replace("\\", "/")
        else:
            record["path"] = record["path"].replace("\\", "/")
        checksum.update(
            json.dumps(
                record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        )
        checksum.update(b"\n")
    return checksum.hexdigest()


def assert_standard_content(path: str) -> None:
    records = json.loads(Path(path).read_bytes())
    assert len(records) == 13068
    assert canonical_digest(records) == STANDARD_DIGEST


def assert_timeline_content(path: str) -> None:
    records = json.loads(Path(path).read_bytes())
    assert len(records) == 126280

    expected_event_types = {
        "M": "modify",
        "A": "access",
        "C": "change",
        "B": "creation",
    }
    attribute_counts = Counter()
    for record in records:
        mft = record["windows"]["mft"]
        macb_type = mft["attribute"]["macb_type"]
        assert record["event"]["type"] == [expected_event_types[macb_type]]
        assert mft["valid_fixup"] is True
        attribute_counts[mft["attribute"]["type"], macb_type] += 1
    assert attribute_counts == {
        (attribute, macb): count
        for attribute, count in (("StandardInformation", 13064), ("FileName", 18506))
        for macb in "MACB"
    }
    assert canonical_digest(records, timeline=True) == TIMELINE_DIGEST


def timeline_digest_example() -> dict:
    return {
        "event": {"type": ["modify"]},
        "windows": {
            "mft": {
                "record": {"path": "folder/name"},
                "valid_fixup": True,
            }
        },
        "log": {"file": {"path": str(Path("tests/cache/MFT").resolve())}},
    }


def test_native_sample_digest_keeps_record_order():
    records = [
        {"attributes": {}, "path": "sample.txt", "number": number}
        for number in (1, 2)
    ]
    assert canonical_digest(records) != canonical_digest(list(reversed(records)))


@pytest.mark.parametrize("field", ["valid_fixup", "event.type"])
def test_native_sample_digest_keeps_timeline_fields(field):
    original = timeline_digest_example()
    changed = deepcopy(original)
    if field == "valid_fixup":
        changed["windows"]["mft"][field] = False
    else:
        changed["event"]["type"] = ["change"]
    assert canonical_digest([original], timeline=True) != canonical_digest(
        [changed], timeline=True
    )


def test_native_sample_digest_normalizes_only_path_separators():
    original = timeline_digest_example()
    changed = deepcopy(original)
    changed["windows"]["mft"]["record"]["path"] = "folder\\name"
    before = deepcopy(changed)
    assert canonical_digest([original], timeline=True) == canonical_digest(
        [changed], timeline=True
    )
    assert changed == before


def test_native_sample_digest_checks_evidence_path():
    changed = timeline_digest_example()
    changed["log"]["file"]["path"] = "wrong/MFT"
    with pytest.raises(AssertionError):
        canonical_digest([changed], timeline=True)


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
@pytest.mark.usefixtures("prepare_mft")
def test__mft2json_convert(monkeypatch):
    path = "tests/cache/MFT.json"
    argv = ["mft2json", "--no-timeline", "-o", path, "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert_standard_content(path)


@pytest.mark.usefixtures("prepare_mft")
def test__mft2json_convert_multiprocessing(monkeypatch):
    path = "tests/cache/MFT-m.json"
    argv = ["mft2json", "--no-timeline", "-o", path, "-m", "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert_standard_content(path)


@pytest.mark.usefixtures("prepare_mft")
def test__mft2json_timeline_convert(monkeypatch):
    path = "tests/cache/MFT-t.json"
    argv = ["mft2json", "--timeline", "-o", path, "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert_timeline_content(path)


@pytest.mark.usefixtures("prepare_mft")
def test__mft2json_timeline_convert_multiprocessing(monkeypatch):
    path = "tests/cache/MFT-t-m.json"
    argv = ["mft2json", "--timeline", "-o", path, "-m", "tests/cache/MFT"]
    with monkeypatch.context() as m:
        m.setattr("sys.argv", argv)
        m2j()
    assert_timeline_content(path)


@pytest.mark.usefixtures("prepare_mft")
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
        diagnostics = []

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
