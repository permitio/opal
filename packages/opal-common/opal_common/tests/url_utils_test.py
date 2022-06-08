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

from pathlib import Path
from typing import List

from opal_common.urls import set_url_query_param


def test_set_url_query_param():
    base_url = "api.permit.io/opal/data/config"

    # https scheme, query string not empty
    assert (
        set_url_query_param(
            f"https://{base_url}?some=val&other=val2", "token", "secret"
        )
        == f"https://{base_url}?some=val&other=val2&token=secret"
    )

    # http scheme, query string empty
    assert (
        set_url_query_param(f"http://{base_url}", "token", "secret")
        == f"http://{base_url}?token=secret"
    )

    # no scheme, query string empty
    assert (
        set_url_query_param(f"{base_url}", "token", "secret")
        == f"{base_url}?token=secret"
    )

    # no scheme, query string not empty
    assert (
        set_url_query_param(f"{base_url}?some=val", "token", "secret")
        == f"{base_url}?some=val&token=secret"
    )
