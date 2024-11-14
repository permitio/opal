import os
import sys

import pytest

# Add root opal dir to use local src as package for tests (i.e, no need for python -m pytest)
root_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.path.pardir,
        os.path.pardir,
        os.path.pardir,
    )
)
sys.path.append(root_dir)

from pathlib import Path

from opal_common.engine.paths import is_data_module, is_policy_module


def test_is_data_module():
    """Test is_data_module() on different paths."""
    # files that are named data.json are data modules
    assert is_data_module(Path("data.json")) == True
    assert is_data_module(Path("some/dir/to/data.json")) == True

    # json files that are not named data.json are not data modules
    assert is_data_module(Path("other.json")) == False
    assert is_data_module(Path("some/dir/to/other.json")) == False

    # files with other extensions are not data modules
    assert is_data_module(Path("data.txt")) == False

    # directories are not data modules
    assert is_data_module(Path(".")) == False
    assert is_data_module(Path("some/dir/to")) == False


def test_is_policy_module():
    """Test is_policy_module() on different paths."""
    # files with rego extension are rego modules
    assert is_policy_module(Path("some/dir/to/file.rego")) == True
    assert is_policy_module(Path("rbac.rego")) == True

    # files with other extensions are not rego modules
    assert is_policy_module(Path("rbac.json")) == False

    # directories are not data modules
    assert is_policy_module(Path(".")) == False
    assert is_policy_module(Path("some/dir/to")) == False
