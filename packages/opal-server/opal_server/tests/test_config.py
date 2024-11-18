# packages/opal-common/opal_common/tests/test_config.py

import pytest
from opal_server.config import opal_server_config
from opal_common.confi.types import ConfiEntry

def test_server_config_descriptions():
    missing_descriptions = []

    for key, entry in opal_server_config.entries.items():
        if isinstance(entry, ConfiEntry) and not entry.description:
            missing_descriptions.append(key)

    assert not missing_descriptions, f"The following config variables are missing descriptions: {', '.join(missing_descriptions)}"
    
