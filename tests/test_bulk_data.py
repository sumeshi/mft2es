import importlib
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_mixed_data_preserves_values_input_and_ids(monkeypatch):
    module = importlib.import_module("mft2es.models.ElasticsearchUtils")
    monkeypatch.setattr(module, "Elasticsearch", MagicMock())
    client = module.ElasticsearchUtils("localhost", 9200, "http", "", "")
    records = [
        {"attributes": {"DATA": [{"data": value}]}}
        for value in ["resident\n日本語", {"data_runs": []}, "", None]
    ] + [{"@timestamp": "2020-01-01T00:00:00Z"}]
    original = deepcopy(records)
    captured = []

    def bulk(_client, actions, **kwargs):
        captured.extend(actions)
        return len(captured), []

    monkeypatch.setattr(module, "bulk", bulk)
    assert client.bulk_indice(records, "test", "") == (5, [])
    assert records == original
    for record, action in zip(original, captured):
        assert action["_id"] == client.calc_hash(record)
    assert captured[0]["_source"]["attributes"]["DATA"][0]["data"] == {
        "resident_data": "resident\n日本語"
    }
    assert captured[2]["_source"]["attributes"]["DATA"][0]["data"] == {
        "resident_data": ""
    }
    for i in (1, 3, 4):
        assert captured[i]["_source"] == original[i]


@pytest.mark.parametrize("timeline", [False, True])
def test_unsigned_vcn_preserved_without_long_overflow(monkeypatch, timeline):
    module = importlib.import_module("mft2es.models.ElasticsearchUtils")
    monkeypatch.setattr(module, "Elasticsearch", MagicMock())
    client = module.ElasticsearchUtils("localhost", 9200, "http", "", "")
    attribute = {"header": {"residential_header": {
        "vnc_first": 0, "vnc_last": 2**64 - 1
    }}}
    record = ({"windows": {"mft": {"attribute": attribute}}} if timeline else
              {"attributes": {"IndexAllocation": [attribute]}})
    original = deepcopy(record)
    captured = []

    def bulk(_client, actions, **kwargs):
        captured.extend(actions)
        return 1, []

    monkeypatch.setattr(module, "bulk", bulk)
    client.bulk_indice([record], "test", "")
    source = captured[0]["_source"]
    normalized = (source["windows"]["mft"]["attribute"] if timeline else
                  source["attributes"]["IndexAllocation"][0])
    assert normalized["header"]["residential_header"] == {
        "vnc_first": "0x0", "vnc_last": "0xffffffffffffffff"
    }
    assert record == original
    assert captured[0]["_id"] == client.calc_hash(original)


def test_multiple_attributes_keep_values_order_and_hash(monkeypatch):
    module = importlib.import_module("mft2es.models.ElasticsearchUtils")
    monkeypatch.setattr(module, "Elasticsearch", MagicMock())
    client = module.ElasticsearchUtils("localhost", 9200, "http", "", "")
    record = {
        "attributes": {
            "DATA": [
                {"header": {"name": ""}, "data": {"data_runs": []}},
                {"header": {"name": "resident"}, "data": "4142"},
                {"header": {"name": "empty"}, "data": ""},
                {"header": {"name": "null"}, "data": None},
            ],
            "IndexAllocation": [
                {"header": {"residential_header": {"vnc_first": 0}}},
                {"header": {"residential_header": {"vnc_last": 2**64 - 1}}},
            ],
            "FileName": [
                {"data": {"name": "long.txt", "namespace": "Win32"}},
                {"data": {"name": "LONG~1.TXT", "namespace": "DOS"}},
            ],
        }
    }
    original = deepcopy(record)
    expected = deepcopy(record)
    expected["attributes"]["DATA"][1]["data"] = {"resident_data": "4142"}
    expected["attributes"]["DATA"][2]["data"] = {"resident_data": ""}
    expected["attributes"]["IndexAllocation"][0]["header"]["residential_header"] = {
        "vnc_first": "0x0"
    }
    expected["attributes"]["IndexAllocation"][1]["header"]["residential_header"] = {
        "vnc_last": "0xffffffffffffffff"
    }
    captured = []

    def bulk(_client, actions, **kwargs):
        captured.extend(actions)
        return len(captured), []

    monkeypatch.setattr(module, "bulk", bulk)

    assert client.bulk_indice([record], "test", "") == (1, [])
    assert record == original
    assert captured == [
        {"_id": client.calc_hash(original), "_index": "test", "_source": expected}
    ]
    assert client.es.mock_calls == []

    changed = deepcopy(original)
    changed["attributes"]["DATA"][0]["header"]["name"] = "changed-first-stream"
    assert client.calc_hash(changed) != captured[0]["_id"]


def test_bulk_error_reports_cause_and_partial_success(monkeypatch):
    module = importlib.import_module("mft2es.presenters.Mft2esPresenter")
    presenter = module.Mft2esPresenter(Path("unused"), is_quiet=True)
    monkeypatch.setattr(presenter, "mft2es", lambda: iter([[{}]]))
    client = MagicMock()
    client.bulk_indice.return_value = (489, [{"index": {
        "_id": "record-3", "status": 400,
        "error": {"type": "document_parsing_exception", "reason": "type conflict"},
        "data": {"private_payload": "DO_NOT_LOG"},
    }}] * 11)
    monkeypatch.setattr(module, "ElasticsearchUtils", lambda **kwargs: client)
    with pytest.raises(RuntimeError) as error:
        presenter.bulk_import()
    message = str(error.value)
    assert "11 document(s)" in message
    assert "489 indexed" in message
    assert "document_parsing_exception: type conflict" in message
    assert message.count("id=record-3") == 3
    assert "DO_NOT_LOG" not in message
    client.close.assert_called_once()
