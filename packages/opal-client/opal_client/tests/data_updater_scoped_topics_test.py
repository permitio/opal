import os
import sys

import pytest

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
)
sys.path.append(root_dir)

from opal_client.data.updater import DataUpdater


def _updater(scope_id, data_topics):
    # Only the attributes the topic matcher reads; no server or policy store needed
    updater = DataUpdater.__new__(DataUpdater)
    updater._scope_id = scope_id
    updater._data_topics = data_topics
    return updater


@pytest.mark.parametrize(
    "entry_topics, expected",
    [
        # entries of the scope's data sources config carry the scoped form
        (["acme:data:documents"], True),
        # entries of an update published through POST /scopes/acme/data/update
        (["data:documents"], True),
        # another scope's topic, or a topic this client does not subscribe to
        (["other:data:documents"], False),
        (["data:users"], False),
        (["acme:data:users"], False),
    ],
)
def test_scoped_client_matches_scoped_and_unscoped_entry_topics(entry_topics, expected):
    updater = _updater("acme", ["acme:data:documents"])
    assert updater._entry_matches_data_topics(entry_topics) is expected


@pytest.mark.parametrize(
    "entry_topics, expected",
    [
        (["policy_data"], True),
        (["other_data"], False),
        # an unscoped client never rewrites topics
        (["acme:policy_data"], False),
    ],
)
def test_default_scope_matches_topics_unchanged(entry_topics, expected):
    updater = _updater("default", ["policy_data"])
    assert updater._entry_matches_data_topics(entry_topics) is expected
