# config: utf-8
import hashlib
from pathlib import Path
from urllib import request

import pytest

MFT_SAMPLE_URL = (
    "https://raw.githubusercontent.com/omerbenamram/mft/"
    "91db59c676b980b1cfdcb683fa333d10b635ab0f/samples/MFT"
)
MFT_SAMPLE_SHA256 = "c78f4968345b70783fbf6573d86c4bf300295ae26ddde4033dd1037b802e13c1"


@pytest.fixture(scope="session", autouse=False)
def prepare_mft():
    mft = Path(__file__).parent / Path("cache") / ("MFT")
    mft.parent.mkdir(exist_ok=True)
    if (
        not mft.is_file()
        or hashlib.sha256(mft.read_bytes()).hexdigest() != MFT_SAMPLE_SHA256
    ):
        with request.urlopen(MFT_SAMPLE_URL, timeout=30) as response:
            mft.write_bytes(response.read())
    assert hashlib.sha256(mft.read_bytes()).hexdigest() == MFT_SAMPLE_SHA256

    # transition to test cases
    yield

    # teardown
    # remove cache files
    cachedir = Path(__file__).parent / Path("cache")
    for file in cachedir.glob("**/*[!.gitkeep]"):
        file.unlink()
