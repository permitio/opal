"""P3 (PR3 fixes): OPAL_REPO_WATCHER_ENABLED gates the scopes sync task.

The flag reads as "single-repo watcher", but in scopes mode it decides
whether setup_watcher_task() -> ScopesPolicyWatcherTask ever runs — i.e.
whether scopes are synced and purged at all. A fleet booted with it off
registered 2160 scopes, stayed Ready and never cloned a thing (env B
bring-up, 2026-08-18). The server now says so loudly at startup; it does
not refuse to boot.
"""
import pytest
from opal_server import server as server_module
from opal_server.config import opal_server_config
from opal_server.server import OpalServer


class _RecordingLogger:
    """OpalServer.__init__ reconfigures loguru (removes every sink), so a sink
    added by the test does not survive construction; record calls on the
    module's logger reference instead."""

    def __init__(self):
        self.calls = []

    def _rec(self, level):
        def _log(msg, *a, **k):
            self.calls.append((level, str(msg)))

        return _log

    def __getattr__(self, name):
        if name in (
            "info",
            "warning",
            "error",
            "debug",
            "exception",
            "critical",
            "success",
            "trace",
        ):
            return self._rec(name)
        raise AttributeError(name)


@pytest.fixture
def scopes_on(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(
        opal_server_config, "REDIS_URL", "redis://localhost:6379"
    )  # never connected


@pytest.fixture
def warnings(monkeypatch):
    rec = _RecordingLogger()
    monkeypatch.setattr(server_module, "logger", rec)
    return rec.calls


def _build(watcher: bool):
    return OpalServer(
        init_policy_watcher=watcher,
        init_publisher=False,
        broadcaster_uri=None,
        enable_jwks_endpoint=False,
    )


def test_scopes_without_the_watcher_warns_that_nothing_will_sync(scopes_on, warnings):
    _build(watcher=False)
    hits = [
        m
        for lvl, m in warnings
        if lvl == "warning"
        and "OPAL_REPO_WATCHER_ENABLED is off while OPAL_SCOPES is on" in m
    ]
    assert hits, warnings
    assert "never SYNC or PURGE" in hits[0]


def test_scopes_with_the_watcher_is_quiet(scopes_on, warnings):
    _build(watcher=True)
    assert not [m for lvl, m in warnings if "OPAL_REPO_WATCHER_ENABLED" in m]


def test_the_flag_description_mentions_scopes_mode():
    """The config reference (and the generated docs) must tell an operator what
    the flag really controls in scopes mode."""
    from pathlib import Path

    import opal_server.config as cfg

    src = Path(cfg.__file__).read_text()
    block = src[src.index('"REPO_WATCHER_ENABLED"') :]
    block = block[: block.index("\n    )")]  # end of the confi.bool(...) call
    assert "scopes" in block.lower() and "purge" in block.lower(), block
