import os
import sys

import pytest

# Add root opal dir to use local src as package for tests (i.e, no need for python -m pytest)
root_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.path.pardir,
        os.path.pardir,
    )
)
sys.path.append(root_dir)

import os
from pathlib import Path
from typing import List

from ..confi import Confi, confi


def test_confi_strict_mode():
    class TestConfigStrict(Confi):
        CONFIG_VALUE = confi.int("CONFIG_VALUE", 10)

    os.environ["CONFIG_VALUE"] = "not an int"

    with pytest.raises(Exception):
        config = TestConfigStrict()

    class TestConfigNotStrict(Confi):
        DONT_BE_STRICT = confi.bool("DONT_BE_STRICT")
        CONFIG_VALUE = confi.int("CONFIG_VALUE", 10)

    os.environ["CONFIG_VALUE"] = "not an int"
    os.environ["DONT_BE_STRICT"] = "False"

    # shouldn't raise
    config = TestConfigNotStrict(strict_mode=False)

    # shouldn't raise (point at entry with the strict value)
    config = TestConfigNotStrict(strict_mode="DONT_BE_STRICT")
