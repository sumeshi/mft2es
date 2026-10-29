from copy import deepcopy

import pytest

from mft2es.models.Mft2es import format_standard_record


@pytest.mark.parametrize(
    "kind",
    [
        "StandardInformation",
        "FileName",
        "DATA",
        "BITMAP",
        "IndexRoot",
        "IndexAllocation",
        "AttributeList",
        "UnknownType",
    ],
)
@pytest.mark.parametrize("count", [1, 3])
def test_every_attribute_type_is_always_an_array(kind, count):
    original = [
        {
            "header": {"type_code": kind, "instance": index, "name": f"name-{index}"},
            "data": {"value": index},
        }
        for index in range(count)
    ]
    expected = deepcopy(original)
    record = {
        "header": {"record_number": 42},
        "valid_fixup": False,
        "attributes": original,
    }

    result = format_standard_record(record, "resolved.txt", ["case"])

    assert result == {
        "header": {"record_number": 42},
        "valid_fixup": False,
        "attributes": {kind: expected},
        "path": "resolved.txt",
        "tags": ["mft", "case"],
    }
    assert all(
        saved is source for saved, source in zip(result["attributes"][kind], original)
    )


def test_interleaved_attributes_keep_per_type_order_and_duplicates():
    original = [
        {"header": {"type_code": kind, "instance": instance}, "data": {}}
        for kind, instance in [
            ("FileName", 3),
            ("DATA", 5),
            ("FileName", 2),
            ("IndexRoot", 7),
            ("DATA", 5),
            ("FileName", 1),
        ]
    ]

    result = format_standard_record({"attributes": original}, "resolved.txt")
    groups = result["attributes"]

    assert list(groups) == ["FileName", "DATA", "IndexRoot"]
    assert sum(map(len, groups.values())) == len(original)
    assert {
        kind: [attribute["header"]["instance"] for attribute in attributes]
        for kind, attributes in groups.items()
    } == {"FileName": [3, 2, 1], "DATA": [5, 5], "IndexRoot": [7]}
    assert groups["DATA"][0] == groups["DATA"][1]
    assert groups["DATA"][0] is not groups["DATA"][1]
    assert [a["data"] for a in groups["FileName"]] == [{}, {}, {}]


def test_empty_attributes_remain_an_empty_object():
    assert format_standard_record({"attributes": []}, "unused") == {
        "attributes": {},
        "path": "unused",
        "tags": ["mft"],
    }


def test_multiple_data_attributes_keep_payload_values_and_types():
    payloads = ["4142", {"data_runs": [{"lcn": 123, "length": 2}]}, None, ""]
    original = [
        {
            "header": {"type_code": "DATA", "name": name, "instance": index},
            "data": payload,
        }
        for index, (name, payload) in enumerate(
            zip(["", "named-stream", "empty-nonresident", "empty-resident"], payloads)
        )
    ]
    expected = deepcopy(original)

    result = format_standard_record({"attributes": original}, "unused")

    assert result["attributes"]["DATA"] == expected
    assert [type(a["data"]) for a in result["attributes"]["DATA"]] == [
        str,
        dict,
        type(None),
        str,
    ]


@pytest.mark.parametrize("kind", ["DATA", "BITMAP"])
@pytest.mark.parametrize("field", ["vnc_first", "vnc_last"])
def test_vcn_normalization_applies_to_every_attribute(kind, field):
    values = [0, 1, 2**64 - 1, None]
    original = [
        {"header": {"type_code": kind, "residential_header": {field: value}}}
        for value in values
    ]
    original.extend(
        [
            {"header": {"type_code": kind, "residential_header": {}}},
            {"header": {"type_code": kind}},
        ]
    )

    result = format_standard_record({"attributes": original}, "unused")

    assert [
        a["header"].get("residential_header", {}) for a in result["attributes"][kind]
    ] == [
        {field: 0},
        {field: "0x1"},
        {field: "0xffffffffffffffff"},
        {field: None},
        {},
        {},
    ]


def test_other_attribute_vcns_remain_in_their_existing_json_form():
    original = [
        {
            "header": {
                "type_code": "IndexAllocation",
                "residential_header": {
                    "vnc_first": first,
                    "vnc_last": 2**64 - 1,
                },
            }
        }
        for first in (0, 1)
    ]
    expected = deepcopy(original)

    result = format_standard_record({"attributes": original}, "unused")

    assert result["attributes"]["IndexAllocation"] == expected
