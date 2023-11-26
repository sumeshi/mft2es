# config: utf-8
import hashlib
from pathlib import Path
from urllib import request

import pytest


@pytest.fixture(scope='session', autouse=True)
def prepare_mft():
    # setup
    ## download mft sample
    url = 'https://github.com/omerbenamram/mft/raw/master/samples/MFT'
    mft = Path(__file__).parent / Path('cache') / ('MFT')
    data = request.urlopen(url).read()
    with open(mft.resolve(), mode="wb") as f:
        f.write(data)
    mft_md5 = hashlib.md5(mft.read_bytes()).hexdigest()
    assert mft_md5 == 'bdeb39402f18be9824f7c2feb07b7592'

    # transition to test cases
    yield

    # teardown
    ## remove cache files
    cachedir = Path(__file__).parent / Path('cache')
    for file in cachedir.glob('**/*[!.gitkeep]'):
        file.unlink()
