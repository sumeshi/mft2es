"""MFT evidence and ES-only DATA/VCN representation on a real ES service."""

from copy import deepcopy


def expected_source(document):
    source = deepcopy(document)
    attributes = source.get("attributes", {})
    if isinstance(attributes.get("DATA", {}).get("data"), str):
        attributes["DATA"]["data"] = {"resident_data": attributes["DATA"]["data"]}
    candidates = list(attributes.values())
    if "windows" in source:
        candidates.append(source["windows"]["mft"]["attribute"])
    for attribute in candidates:
        header = attribute.get("header", {}).get("residential_header", {})
        for field in ("vnc_first", "vnc_last"):
            if isinstance(header.get(field), int):
                header[field] = hex(header[field])
    return source


def assert_native_documents(documents, mode):
    assert len(documents) == (8 if mode else 2)
    metadata = (
        [document["windows"]["mft"] for document in documents] if mode else documents
    )
    assert all(record["valid_fixup"] is True for record in metadata)
    if mode:
        assert {record["attribute"]["macb_type"] for record in metadata} == {
            "M",
            "A",
            "C",
            "B",
        }


def run_extra_cases(client, transport, new_index, stored_documents, document_id):
    standard = [
        {"valid_fixup": True, "attributes": {"DATA": {"data": "4142"}}},
        {
            "valid_fixup": False,
            "attributes": {
                "DATA": {
                    "header": {
                        "residential_header": {"vnc_first": 0, "vnc_last": 2**64 - 1}
                    },
                    "data": {"data_runs": []},
                }
            },
        },
    ]
    timeline = [
        {
            "@timestamp": "2026-01-01T00:00:00Z",
            "windows": {
                "mft": {
                    "valid_fixup": status,
                    "attribute": {
                        "header": {
                            "residential_header": {
                                "vnc_first": 0,
                                "vnc_last": 2**64 - 1,
                            }
                        }
                    },
                }
            },
        }
        for status in (True, False, None)
    ]
    for label, documents in (("data", standard), ("fixup", timeline)):
        original = deepcopy(documents)
        index = new_index(label)
        assert transport.bulk_indice(documents, index) == (len(documents), [])
        actual = stored_documents(client, index)
        assert actual == {
            document_id(record): expected_source(record) for record in original
        }
        assert documents == original
        if label == "fixup":
            states = [
                actual[document_id(record)]["windows"]["mft"]["valid_fixup"]
                for record in original
            ]
            assert states == [True, False, None]
            assert (
                client.count(
                    index=index, query={"exists": {"field": "windows.mft.valid_fixup"}}
                )["count"]
                == 2
            )
        else:
            assert actual[document_id(original[0])]["attributes"]["DATA"]["data"] == {
                "resident_data": "4142"
            }
            header = actual[document_id(original[1])]["attributes"]["DATA"]["header"][
                "residential_header"
            ]
            assert header == {"vnc_first": "0x0", "vnc_last": "0xffffffffffffffff"}
