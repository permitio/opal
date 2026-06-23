from opal_server.config import OpalServerConfig


def test_git_resilience_config_defaults():
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_GIT_FETCH_TIMEOUT == 120.0
    assert clean.SCOPES_GIT_MAX_WORKERS == 10
