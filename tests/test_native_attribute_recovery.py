"""Recover native attribute/path failures without losing neighboring evidence."""

import json
import os
import struct
import subprocess
import sys
import warnings

import pytest

from mft2es.models.Mft2es import Mft2es
from test_zero_length_recovery import _API_PROBE, _numbers, _record, _seal, _unfix

_PROBE_LIMITS = """
import sys
if sys.platform.startswith('linux'):
    import resource
    if hasattr(resource, 'RLIMIT_AS'):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    if hasattr(resource, 'RLIMIT_CORE'):
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
"""


def _probe(source, multiprocess=False, timeline=False, chunk_size=500):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE_LIMITS + _API_PROBE,
            str(source),
            str(multiprocess),
            str(timeline),
            str(chunk_size),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHON_CPU_COUNT": "2"},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _append_attribute(record, attribute):
    record = _unfix(record)
    offset = struct.unpack_from("<H", record, 20)[0]
    while struct.unpack_from("<I", record, offset)[0] != 0xFFFFFFFF:
        offset += struct.unpack_from("<I", record, offset + 4)[0]
    record[offset : offset + len(attribute)] = attribute
    struct.pack_into("<I", record, offset + len(attribute), 0xFFFFFFFF)
    struct.pack_into("<I", record, 24, offset + len(attribute) + 4)
    return _seal(record)


def _with_attribute_list(record, entry_length=0, *, named=False):
    payload = struct.pack("<IHBBQQH", 0x10, entry_length, 0, 26, 0, 0, 1)
    name = "x".encode("utf-16le") if named else b""
    content_offset = 24 + len(name)
    length = (content_offset + len(payload) + 7) // 8 * 8
    attribute = (
        struct.pack(
            "<IIBBHHHIHBB",
            0x20,
            length,
            0,
            len(name) // 2,
            24 if name else 0,
            0,
            2,
            len(payload),
            content_offset,
            0,
            0,
        )
        + name
        + payload
    )
    return _append_attribute(record, attribute.ljust(length, b"\0"))


def _with_bad_namespace(record, *, retain_filename=False):
    bad = _unfix(record)
    offset = struct.unpack_from("<H", bad, 20)[0]
    bad[offset + 24 + 65] = 4
    result = _seal(bad)
    if retain_filename:
        good = _unfix(_record(1, "retained.txt"))
        start = struct.unpack_from("<H", good, 20)[0]
        length = struct.unpack_from("<I", good, start + 4)[0]
        result = _append_attribute(result, good[start : start + length])
    return result


def _parent_record(number, parent):
    record = _unfix(_record(number, f"{number}.txt"))
    struct.pack_into("<H", record, 22, 3)
    offset = struct.unpack_from("<H", record, 20)[0]
    struct.pack_into("<Q", record, offset + 24, parent)
    return _seal(record)


def _payload(scenario):
    if scenario == "nested":
        middle = _with_attribute_list(_record(1, "bad.txt"))
        return _record(0, "first.txt") + middle + _record(2, "last.txt")
    if scenario == "attributes":
        middle = _with_bad_namespace(_record(1, "bad.txt"))
        return _record(0, "first.txt") + middle + _record(2, "last.txt")
    assert scenario == "cycle"
    return b"".join(_parent_record(i, parent) for i, parent in enumerate((1, 2, 1, 5)))


@pytest.mark.parametrize("scenario", ["nested", "attributes", "cycle"])
@pytest.mark.parametrize("multiprocess", [False, True])
@pytest.mark.parametrize("timeline", [False, True])
@pytest.mark.parametrize("chunk_size", [1, 500])
def test_native_failures_recover_records_and_report_partial_extraction(
    tmp_path, scenario, multiprocess, timeline, chunk_size
):
    source = tmp_path / "recovery-MFT"
    payload = _payload(scenario)
    source.write_bytes(payload)

    result = _probe(source, multiprocess, timeline, chunk_size)

    assert result["partial"] is True
    expected = (
        [0, 2]
        if scenario == "nested" or (scenario == "attributes" and timeline)
        else list(range(4 if scenario == "cycle" else 3))
    )
    assert _numbers(result["records"], timeline) == [
        number for number in expected for _ in range(4 if timeline else 1)
    ]
    assert len(result["diagnostics"]) == 1
    diagnostic = result["diagnostics"][0]
    assert diagnostic["source_file"] == str(source.resolve())
    if scenario == "nested":
        assert diagnostic["record_index"] == 1
        assert diagnostic["stage"] == "parse"
        assert "zero AttributeList entry RecordLength" in diagnostic["error"]
    elif scenario == "attributes":
        assert diagnostic["record_index"] == diagnostic["record_number"] == 1
        assert diagnostic["stage"] == "attributes"
        assert "Unknown filename namespace 4" in diagnostic["error"]
    else:
        assert diagnostic["record_index"] == diagnostic["record_number"] == 0
        assert diagnostic["stage"] == "path"
        assert "parent reference cycle" in diagnostic["error"]
        paths = [
            (
                record["windows"]["mft"]["record"]["path"]
                if timeline
                else record["attributes"]["FileName"]["data"]["path"]
            )
            for record in result["records"]
        ]
        assert all("[Unknown]" in path for path in paths[: 3 * (4 if timeline else 1)])
        assert all(
            path.endswith("3.txt") for path in paths[3 * (4 if timeline else 1) :]
        )
    assert source.read_bytes() == payload


@pytest.mark.parametrize("named", [False, True])
@pytest.mark.parametrize("entry_length", [0, 26])
def test_named_and_unnamed_attribute_lists_follow_native_content_cursor(
    tmp_path, named, entry_length
):
    source = tmp_path / "named-list-MFT"
    payload = _with_attribute_list(_record(0, "list.txt"), entry_length, named=named)
    source.write_bytes(payload + _record(1, "last.txt"))

    result = _probe(source)

    assert result["partial"] is (entry_length == 0)
    assert _numbers(result["records"]) == ([1] if entry_length == 0 else [0, 1])
    if entry_length:
        attribute = result["records"][0]["attributes"]["AttributeList"]
        assert attribute["header"]["name"] == ("x" if named else "")
        assert attribute["data"]["entries"][0]["record_length"] == 26
    assert source.read_bytes() == payload + _record(1, "last.txt")


@pytest.mark.parametrize("timeline", [False, True])
def test_bad_attribute_keeps_other_attributes_from_the_same_record(tmp_path, timeline):
    source = tmp_path / "mixed-attributes-MFT"
    payload = (
        _record(0, "first.txt")
        + _with_bad_namespace(_record(1, "bad.txt"), retain_filename=True)
        + _record(2, "last.txt")
    )
    source.write_bytes(payload)

    result = _probe(source, multiprocess=True, timeline=timeline, chunk_size=1)

    assert result["partial"] is True
    assert _numbers(result["records"], timeline) == [
        number for number in range(3) for _ in range(4 if timeline else 1)
    ]
    middle = result["records"][4 if timeline else 1]
    filename = (
        middle["windows"]["mft"]["attribute"]["data"]["name"]
        if timeline
        else middle["attributes"]["FileName"]["data"]["name"]
    )
    assert filename == "retained.txt"
    assert len(result["diagnostics"]) == 1
    assert result["diagnostics"][0]["stage"] == "attributes"
    assert source.read_bytes() == payload


def test_changing_only_the_cyclic_parent_to_root_is_successful(tmp_path):
    source = tmp_path / "noncyclic-MFT"
    payload = b"".join(_parent_record(i, parent) for i, parent in enumerate((1, 2, 5)))
    source.write_bytes(payload)

    result = _probe(source, chunk_size=1)

    assert result["partial"] is False
    assert _numbers(result["records"]) == [0, 1, 2]
    paths = [
        record["attributes"]["FileName"]["data"]["path"] for record in result["records"]
    ]
    assert [path.replace("\\", "/") for path in paths] == [
        "2.txt/1.txt/0.txt",
        "2.txt/1.txt",
        "2.txt",
    ]
    assert source.read_bytes() == payload


@pytest.mark.parametrize("cyclic", [False, True])
def test_long_parent_chain_checks_for_cycles_before_native_recursion(tmp_path, cyclic):
    source = tmp_path / "long-parent-chain-MFT"
    # Keep physical entry 5 outside the chain: native treats parent 5 as root.
    first, last = 10, 137
    records = [_parent_record(0, first)] + [bytes(1024)] * (first - 1)
    records.extend(
        _parent_record(number, number + 1 if number < last else first if cyclic else 5)
        for number in range(first, last + 1)
    )
    payload = b"".join(records)
    source.write_bytes(payload)

    result = _probe(source, multiprocess=True, chunk_size=1)

    assert result["partial"] is cyclic
    assert _numbers(result["records"]) == [0, *range(first, last + 1)]
    paths = [
        record["attributes"]["FileName"]["data"]["path"] for record in result["records"]
    ]
    if cyclic:
        assert any(error["stage"] == "path" for error in result["diagnostics"])
        assert "[Unknown]" in paths[0]
    else:
        expected = "/".join(
            [f"{number}.txt" for number in range(last, first - 1, -1)] + ["0.txt"]
        )
        assert paths[0].replace("\\", "/") == expected
        assert result["diagnostics"] == []
    assert source.read_bytes() == payload


def test_parent_prewalk_guards_nested_lists_before_isolated_native_parsing(tmp_path):
    source = tmp_path / "long-chain-with-bad-list-MFT"
    first, last, damaged = 10, 137, 80
    records = [_parent_record(0, first)] + [bytes(1024)] * (first - 1)
    records.extend(
        _parent_record(number, number + 1 if number < last else 5)
        for number in range(first, last + 1)
    )
    records[damaged] = _with_attribute_list(records[damaged])
    payload = b"".join(records)
    source.write_bytes(payload)

    result = _probe(source, multiprocess=True, chunk_size=1)

    assert result["partial"] is True
    assert _numbers(result["records"]) == [
        0,
        *(number for number in range(first, last + 1) if number != damaged),
    ]
    assert len(result["diagnostics"]) == 1
    assert result["diagnostics"][0]["stage"] == "parse"
    assert "zero AttributeList entry RecordLength" in result["diagnostics"][0]["error"]
    assert source.read_bytes() == payload


@pytest.mark.parametrize("base_reference", [False, True])
def test_filename_self_reference_and_base_self_reference_have_distinct_behavior(
    tmp_path, base_reference
):
    source = tmp_path / "self-reference-MFT"
    if base_reference:
        record = _unfix(_record(1, None))
        struct.pack_into("<Q", record, 32, 1)
        record = _seal(record)
    else:
        record = _parent_record(1, 1)
    payload = _record(0, "first.txt") + record
    source.write_bytes(payload)

    result = _probe(source, chunk_size=1)

    assert result["partial"] is base_reference
    assert _numbers(result["records"]) == [0, 1]
    if base_reference:
        assert result["diagnostics"][0]["stage"] == "path"
    else:
        assert (
            "[Orphaned]"
            in result["records"][1]["attributes"]["FileName"]["data"]["path"]
        )
    assert source.read_bytes() == payload


def test_recovered_cycle_releases_native_parser_before_foreign_thread_gc(tmp_path):
    source = tmp_path / "cycle-gc-MFT"
    source.write_bytes(_payload("cycle"))
    code = _PROBE_LIMITS + """
import gc,sys,threading,weakref
from mft2es.models.Mft2es import Mft2es
unraisable=[]
sys.unraisablehook=lambda error: unraisable.append(str(error.exc_value))
gc.collect()
gc.disable()
model=Mft2es(sys.argv[1])
reference=weakref.ref(model)
records=[record for chunk in model.gen_timeline_records(False,1,False) for record in chunk]
assert len(records)==4 and model.diagnostics
model.close()
del model
assert reference() is None
collector=threading.Thread(target=gc.collect)
collector.start()
collector.join()
assert not unraisable, unraisable
print('ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(source)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


@pytest.mark.parametrize("multiprocess", [False, True])
def test_rereading_a_skipped_zero_parent_is_not_a_reference_cycle(
    tmp_path, multiprocess
):
    source = tmp_path / "zero-parent-MFT"
    payload = _record(0, "first.txt") + bytes(1024) + _parent_record(2, 1)
    source.write_bytes(payload)

    result = _probe(source, multiprocess=multiprocess, chunk_size=1)

    assert result["partial"] is False
    assert result["diagnostics"] == []
    assert _numbers(result["records"]) == [0, 2]
    assert source.read_bytes() == payload


@pytest.mark.parametrize("size_field", [0, 2048])
def test_attribute_inspector_keeps_later_record_size_field_unchanged(
    tmp_path, size_field
):
    source = tmp_path / "later-size-MFT"
    middle = bytearray(_record(1, "middle.txt"))
    struct.pack_into("<I", middle, 28, size_field)
    payload = _record(0, "first.txt") + middle + _record(2, "last.txt")
    source.write_bytes(payload)

    result = _probe(source, chunk_size=1)

    assert result["partial"] is False
    assert _numbers(result["records"]) == [0, 1, 2]
    assert result["records"][1]["header"]["total_entry_size"] == size_field
    assert source.read_bytes() == payload


def test_attribute_inspector_does_not_duplicate_fixup_warning(tmp_path):
    source = tmp_path / "fixup-warning-MFT"
    mismatch = bytearray(_record(1, "mismatch.txt"))
    mismatch[510:512] = b"\x02\0"
    payload = _record(0, "first.txt") + mismatch + _record(2, "last.txt")
    source.write_bytes(payload)
    parser = Mft2es(source)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            records = [
                record
                for chunk in parser.gen_timeline_records(False, 1, False)
                for record in chunk
            ]
    finally:
        parser.close()

    fixup_warnings = [
        warning
        for warning in caught
        if "fixup bytes are not equal" in str(warning.message)
    ]
    # JSON and CSV each parse the original record. The inspector adds none.
    assert len(fixup_warnings) == 2
    assert all("[entry: 1]" in str(warning.message) for warning in fixup_warnings)
    assert _numbers(records) == [0, 1, 2]
    assert records[1]["valid_fixup"] is False
    assert parser.diagnostics == []
    assert source.read_bytes() == payload


@pytest.mark.parametrize("scenario", ["nested", "attributes", "cycle"])
@pytest.mark.parametrize("output_format", ["json", "jsonl"])
@pytest.mark.parametrize("multiprocess", [False, True])
def test_cli_publishes_recovered_output_and_fails_for_native_errors(
    tmp_path, scenario, output_format, multiprocess
):
    source = tmp_path / "cli-recovery-MFT"
    payload = _payload(scenario)
    source.write_bytes(payload)
    output = tmp_path / f"output.{output_format}"
    command = [
        sys.executable,
        "-c",
        _PROBE_LIMITS
        + "from mft2es.views.Mft2jsonView import entry_point; entry_point()",
        str(source),
        "--quiet",
        "--format",
        output_format,
        "-o",
        str(output),
    ]
    if multiprocess:
        command.append("--multiprocess")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHON_CPU_COUNT": "2"},
    )

    assert result.returncode == 1, result.stderr
    assert "Partial extraction" in result.stderr
    records = (
        json.loads(output.read_bytes())
        if output_format == "json"
        else [json.loads(line) for line in output.read_bytes().splitlines()]
    )
    expected = [0, 1, 2, 3] if scenario == "cycle" else [0, 2]
    assert _numbers(records, True) == [number for number in expected for _ in range(4)]
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))
    assert source.read_bytes() == payload
