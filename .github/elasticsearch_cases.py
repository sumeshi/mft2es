"""MFT evidence and ES-only DATA/VCN representation on a real ES service."""

from copy import deepcopy
import os
from pathlib import Path
import runpy
import shutil
from tempfile import TemporaryDirectory


def expected_source(document):
    source = deepcopy(document)
    attributes = source.get("attributes", {})
    for attribute in attributes.get("DATA", []):
        if isinstance(attribute.get("data"), str):
            attribute["data"] = {"resident_data": attribute["data"]}
    candidates = [attribute for group in attributes.values() for attribute in group]
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
    else:
        assert all(
            isinstance(group, list) and group
            for document in documents
            for group in document["attributes"].values()
        )


def run_extra_cases(client, transport, new_index, stored_documents, document_id):
    from mft2es import mft2json

    artifact = runpy.run_path(str(Path(__file__).with_name("artifact_fixture.py")))
    with TemporaryDirectory() as directory:
        source = artifact["create_multi_attribute_artifact"](Path(directory))
        native = mft2json(str(source), timeline_mode=False, multiprocess=False)
    assert len(native) == 1 and native[0]["valid_fixup"] is True
    assert native[0]["path"] == "Long name.txt"
    attributes = native[0]["attributes"]
    assert [
        attribute["header"]["instance"] for attribute in attributes["FileName"]
    ] == [1, 2]
    assert [attribute["data"]["name"] for attribute in attributes["FileName"]] == [
        "Long name.txt",
        "LONGNA~1.TXT",
    ]
    assert all("path" not in attribute["data"] for attribute in attributes["FileName"])
    assert [
        (attribute["header"]["name"], attribute["data"])
        for attribute in attributes["DATA"]
    ] == [("", "4142"), ("metadata", "4344")]
    original_native = deepcopy(native)
    native_index = new_index("native-arrays")
    assert transport.bulk_indice(native, native_index) == (1, [])
    assert native == original_native
    assert stored_documents(client, native_index) == {
        document_id(record): expected_source(record) for record in original_native
    }
    for field, values in (
        ("path.keyword", ("Long name.txt",)),
        ("attributes.FileName.data.name.keyword", ("Long name.txt", "LONGNA~1.TXT")),
        ("attributes.DATA.header.name.keyword", ("", "metadata")),
        ("attributes.DATA.data.resident_data.keyword", ("4142", "4344")),
    ):
        for value in values:
            assert (
                client.count(index=native_index, query={"term": {field: value}})[
                    "count"
                ]
                == 1
            )

    if os.name == "posix":
        from mft2es import PartialExtractionError

        with TemporaryDirectory() as path_directory:
            path_directory = Path(path_directory)
            path_source = artifact["create_multi_attribute_artifact"](path_directory)
            # Byte-decoded and literal backslash paths share a display value.
            # Retained source bytes keep their document IDs distinct in ES.
            raw_directory = os.fsencode(path_directory) + b"/source-\xff"
            os.mkdir(raw_directory)
            raw_path = Path(os.fsdecode(raw_directory)) / "MFT"
            shutil.copyfile(path_source, raw_path)
            literal_path = path_directory / "source-\\udcff" / "MFT"
            literal_path.parent.mkdir()
            shutil.copyfile(path_source, literal_path)
            raw_documents = mft2json(
                str(raw_path), timeline_mode=True, multiprocess=False
            )
            literal_documents = mft2json(
                str(literal_path), timeline_mode=True, multiprocess=False
            )
            assert raw_documents and literal_documents
            assert (
                raw_documents[0]["log"]["file"]["path"]
                == literal_documents[0]["log"]["file"]["path"]
            )
            expected_bytes = os.fsencode(str(raw_path.resolve())).hex()
            assert all(
                document["windows"]["mft"]["source"]["file_path_bytes_hex"]
                == expected_bytes
                for document in raw_documents
            )
            assert all(
                "source" not in document["windows"]["mft"]
                for document in literal_documents
            )
            path_index = new_index("path-bytes")
            path_documents = [*raw_documents, *literal_documents]
            assert transport.bulk_indice(path_documents, path_index) == (
                len(path_documents),
                [],
            )
            ids = [document_id(document) for document in path_documents]
            assert len(set(ids)) == len(ids)
            assert set(stored_documents(client, path_index)) == set(ids)

            truncated_path = path_directory / "truncated.mft"
            truncated_payload = (
                path_source.read_bytes() + path_source.read_bytes()[:512]
            )
            truncated_path.write_bytes(truncated_payload)
            try:
                mft2json(str(truncated_path), timeline_mode=True, multiprocess=False)
            except PartialExtractionError as error:
                partial_records = error.records
                assert len(error.diagnostics) == 1
                assert "byte offset" in error.diagnostics[0]["error"]
            else:
                raise AssertionError("truncated MFT tail was not reported")
            truncated_index = new_index("truncated-tail")
            assert transport.bulk_indice(partial_records, truncated_index) == (
                len(partial_records),
                [],
            )
            assert set(stored_documents(client, truncated_index)) == {
                document_id(document) for document in partial_records
            }

    standard = [
        {
            "valid_fixup": True,
            "attributes": {
                "DATA": [
                    {"header": {"name": ""}, "data": {"data_runs": []}},
                    {"header": {"name": "Roxio EMC Stream"}, "data": "4142"},
                    {"header": {"name": "empty"}, "data": ""},
                    {"header": {"name": "null"}, "data": None},
                ],
                "FileName": [
                    {"data": {"name": "Long name.txt"}},
                    {"data": {"name": "LONGNA~1.TXT"}},
                ],
                "IndexAllocation": [
                    {"header": {"residential_header": {"vnc_first": 0}}},
                    {"header": {"residential_header": {"vnc_last": 2**64 - 1}}},
                ],
            },
        },
        {
            "valid_fixup": False,
            "attributes": {
                "DATA": [
                    {
                        "header": {
                            "residential_header": {
                                "vnc_first": 0,
                                "vnc_last": 2**64 - 1,
                            }
                        },
                        "data": {"data_runs": []},
                    }
                ]
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
        legacy = None
        if label == "data":
            # The fixture establishes a pre-existing object mapping. The
            # transport must accept arrays without managing that mapping.
            legacy = {
                "attributes": {
                    "DATA": {
                        "header": {"name": "legacy"},
                        "data": {"resident_data": "00"},
                    },
                    "FileName": {"data": {"name": "legacy.txt"}},
                }
            }
            seeded = client.bulk(
                operations=[
                    {"index": {"_index": index, "_id": "legacy-object"}},
                    legacy,
                ]
            )
            assert not seeded["errors"]
            properties = client.indices.get_mapping(index=index)[index]["mappings"][
                "properties"
            ]["attributes"]["properties"]
            assert properties["DATA"].get("type", "object") == "object"
            assert properties["FileName"].get("type", "object") == "object"
        assert transport.bulk_indice(documents, index) == (len(documents), [])
        actual = stored_documents(client, index)
        expected = {document_id(record): expected_source(record) for record in original}
        if legacy is not None:
            expected["legacy-object"] = legacy
        assert actual == expected
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
            assert actual[document_id(original[0])]["attributes"]["DATA"][1][
                "data"
            ] == {"resident_data": "4142"}
            header = actual[document_id(original[1])]["attributes"]["DATA"][0][
                "header"
            ]["residential_header"]
            assert header == {"vnc_first": "0x0", "vnc_last": "0xffffffffffffffff"}
            for name in ("", "Roxio EMC Stream", "empty", "null"):
                assert (
                    client.count(
                        index=index,
                        query={"term": {"attributes.DATA.header.name.keyword": name}},
                    )["count"]
                    == 1
                )
            for name in ("Long name.txt", "LONGNA~1.TXT"):
                assert (
                    client.count(
                        index=index,
                        query={"term": {"attributes.FileName.data.name.keyword": name}},
                    )["count"]
                    == 1
                )
            aggregation = client.search(
                index=index,
                size=0,
                aggregations={
                    "streams": {
                        "terms": {"field": "attributes.DATA.header.name.keyword"}
                    }
                },
            )
            assert {
                bucket["key"]: bucket["doc_count"]
                for bucket in aggregation["aggregations"]["streams"]["buckets"]
            } == {"legacy": 1, "": 1, "Roxio EMC Stream": 1, "empty": 1, "null": 1}
