import pytest
from opal_client.config import opal_client_config
from opal_common.config import opal_common_config
from opal_server.config import opal_server_config


def test_opal_common_config_descriptions():
    for name, entry in opal_common_config.entries.items():
        assert entry.description is not None, f"{name} is missing a description"


def test_opal_client_config_descriptions():
    for name, entry in opal_client_config.entries.items():
        assert entry.description is not None, f"{name} is missing a description"


def test_opal_server_config_descriptions():
    for name, entry in opal_server_config.entries.items():
        assert entry.description is not None, f"{name} is missing a description"
