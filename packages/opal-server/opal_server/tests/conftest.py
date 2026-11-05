"""Fixtures shared by the opal-server tests."""
import opal_server.scopes.task as task_module
import pytest
from opal_server.config import opal_server_config


class NoScopes:
    """A ScopeRepository with no scopes."""

    def __init__(self, db):
        pass

    async def all(self):
        return []


@pytest.fixture
def preload_sandbox(monkeypatch, tmp_path):
    """For tests that run ScopesPolicyWatcherTask.preload_scopes: no scopes,
    and a BASE_DIR under tmp_path.

    The preload runs the hung-clone sweep on BASE_DIR before its sync,
    so without this the sweep would remove markers, or with
    SCOPES_GIT_RECLONE_HUNG_ON_START set in the environment delete
    clones, in the default BASE_DIR of whoever runs the tests.
    """
    monkeypatch.setattr(task_module, "ScopeRepository", NoScopes)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
