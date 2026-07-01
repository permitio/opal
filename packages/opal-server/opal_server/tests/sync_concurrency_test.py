from opal_server.config import OpalServerConfig


def test_sync_concurrency_default():
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_SYNC_CONCURRENCY == 10
