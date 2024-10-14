import pytest
from opal_common.config import opal_common_config
from opal_common.confi.types import ConfiEntry


def test_common_config_descriptions():
    missing_descriptions = []

    for key, entry in opal_common_config.entries.items():
        if isinstance(entry, ConfiEntry) and not entry.description:
            missing_descriptions.append(key)

    assert not missing_descriptions, f"The following config variables are missing descriptions: {', '.join(missing_descriptions)}"