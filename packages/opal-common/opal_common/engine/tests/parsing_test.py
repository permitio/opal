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

from opal_common.engine.parsing import get_rego_package


def test_can_extract_the_correct_package_name():
    """The different variations of package names (with real examples from opa
    playground)"""
    # package in first line, no dots
    source_rego = os.path.join(os.path.dirname(__file__), "fixtures/play.rego")
    with open(source_rego, "r") as f:
        contents = f.read()
        assert get_rego_package(contents) == "play"

    # package after comments, two part name
    source_rego = os.path.join(os.path.dirname(__file__), "fixtures/rbac.rego")
    with open(source_rego, "r") as f:
        contents = f.read()
        assert get_rego_package(contents) == "app.rbac"

    # package after comments, three part name
    source_rego = os.path.join(os.path.dirname(__file__), "fixtures/jwt.rego")
    with open(source_rego, "r") as f:
        contents = f.read()
        assert get_rego_package(contents) == "envoy.http.jwt"


def test_no_package_name_in_file():
    """test no package name in module or invalid package."""
    # package line was removed
    source_rego = os.path.join(os.path.dirname(__file__), "fixtures/no-package.rego")
    with open(source_rego, "r") as f:
        contents = f.read()
        assert get_rego_package(contents) is None

    # package line with invalid contents
    source_rego = os.path.join(
        os.path.dirname(__file__), "fixtures/invalid-package.rego"
    )
    with open(source_rego, "r") as f:
        contents = f.read()
        assert get_rego_package(contents) is None

    # empty file
    assert get_rego_package("") is None
