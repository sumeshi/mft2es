import importlib
import threading
from multiprocessing.pool import ThreadPool
from pathlib import Path

import pytest


@pytest.mark.parametrize("timeline", [False, True])
def test_parser_stays_on_owner_thread_with_bounded_ordered_work(monkeypatch, timeline):
    module = importlib.import_module("mft2es.models.Mft2es")
    owner = threading.get_ident()
    consumed = []

    class Parser:
        def entries_json(self):
            assert threading.get_ident() == owner
            for i in range(30):
                assert threading.get_ident() == owner
                consumed.append(i)
                yield str(i)

        def entries_csv(self):
            assert threading.get_ident() == owner
            for i in range(30):
                assert threading.get_ident() == owner
                yield str(i).encode()

    class Context:
        Pool = ThreadPool

    def worker(args):
        assert threading.get_ident() != owner
        j, c, path, mode, tags, offset = args
        assert mode == timeline
        assert tags == ["test"]
        assert offset == int(j[0])
        return [int(value) for value in j], []

    parser = module.Mft2es.__new__(module.Mft2es)
    parser.path = Path("unused")
    parser.parser = parser.csvparser = Parser()
    monkeypatch.setattr(parser, "get_multiprocessing_context", lambda: Context())
    monkeypatch.setattr(parser, "get_cpu_count", lambda: 2)
    monkeypatch.setattr(module, "_mp_worker", worker)
    batches = parser.gen_timeline_records(True, 2, timeline, ["test"])
    first = next(batches)
    assert len(consumed) <= 8
    assert first + [i for batch in batches for i in batch] == list(range(30))
