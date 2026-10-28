"""The ES fixture exercises repeated attributes through the real MFT parser."""

from collections import Counter
from pathlib import Path
import runpy

from mft2es import mft2json
import pytest

FIXTURE = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / ".github" / "artifact_fixture.py")
)


def test_native_multiple_attributes_preserve_instances_names_and_data(tmp_path):
    path = FIXTURE["create_multi_attribute_artifact"](tmp_path)

    records = mft2json(str(path), timeline_mode=False, multiprocess=False)

    assert path.stat().st_size == 1024
    assert len(records) == 1 and records[0]["valid_fixup"] is True
    assert records[0]["path"] == "Long name.txt"
    attributes = records[0]["attributes"]
    assert list(attributes) == ["FileName", "DATA"]
    assert [item["header"]["instance"] for item in attributes["FileName"]] == [1, 2]
    assert [
        (item["data"]["name"], item["data"]["namespace"])
        for item in attributes["FileName"]
    ] == [("Long name.txt", "Win32"), ("LONGNA~1.TXT", "DOS")]
    assert all("path" not in item["data"] for item in attributes["FileName"])
    assert [
        (item["header"]["instance"], item["header"]["name"], item["data"])
        for item in attributes["DATA"]
    ] == [(3, "", "4142"), (4, "metadata", "4344")]


def test_native_multiple_filenames_keep_timeline_events(tmp_path):
    path = FIXTURE["create_multi_attribute_artifact"](tmp_path)

    records = mft2json(str(path), timeline_mode=True, multiprocess=False)

    assert len(records) == 8
    assert Counter(
        (
            record["windows"]["mft"]["attribute"]["data"]["name"],
            record["windows"]["mft"]["attribute"]["macb_type"],
        )
        for record in records
    ) == Counter(
        (name, macb) for name in ("Long name.txt", "LONGNA~1.TXT") for macb in "MACB"
    )


@pytest.mark.parametrize("timeline, expected_count", [(False, 2), (True, 8)])
def test_default_native_fixture_keeps_existing_counts(
    tmp_path, timeline, expected_count
):
    path = FIXTURE["create_artifact"](tmp_path)

    records = mft2json(str(path), timeline_mode=timeline, multiprocess=False)

    assert len(records) == expected_count
