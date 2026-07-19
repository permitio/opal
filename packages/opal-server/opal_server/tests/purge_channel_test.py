from opal_server.config import OpalServerConfig


def test_purge_channel_config_default():
    clean = OpalServerConfig(prefix="OPAL_")
    assert clean.SCOPES_PURGE_CHANNEL == "__opal_scope_purge__"
