import pytest

from mft2es.models.Mft2es import Mft2es, generate_chunks
from mft2es.presenters.Mft2esPresenter import Mft2esPresenter
from mft2es.presenters.Mft2jsonPresenter import Mft2jsonPresenter


@pytest.mark.parametrize("chunk_size", [0, -1, True, 1.5])
def test_model_helpers_reject_invalid_chunk_sizes(chunk_size):
    with pytest.raises(ValueError, match="greater than zero"):
        list(generate_chunks(chunk_size, []))

    model = object.__new__(Mft2es)
    with pytest.raises(ValueError, match="greater than zero"):
        list(model.gen_timeline_records(False, chunk_size))


@pytest.mark.parametrize("presenter", [Mft2esPresenter, Mft2jsonPresenter])
@pytest.mark.parametrize("chunk_size", [0, -1])
def test_presenters_reject_invalid_chunk_sizes_before_io(presenter, chunk_size, tmp_path):
    output = tmp_path / "existing.json"
    output.write_bytes(b"sentinel")
    with pytest.raises(ValueError, match="greater than zero"):
        args = (tmp_path / "missing.mft",) if presenter is Mft2esPresenter else (
            tmp_path / "missing.mft", output
        )
        presenter(*args, chunk_size=chunk_size)
    assert output.read_bytes() == b"sentinel"


def test_public_apis_reject_invalid_chunk_sizes_before_opening_input(tmp_path):
    import mft2es as api

    for convert in (api.mft2es, api.mft2json):
        for chunk_size in (0, -1, True, False, 1.5, "2", None):
            with pytest.raises(ValueError, match="greater than zero"):
                convert(str(tmp_path / "missing.mft"), chunk_size=chunk_size)
