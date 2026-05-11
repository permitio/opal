import asyncio

from opal_server import server as server_module
from opal_server.server import OpalServer


class CapturingLogger:
    def __init__(self):
        self.errors = []
        self.infos = []

    def error(self, message, **kwargs):
        self.errors.append((message, kwargs))

    def info(self, message, **kwargs):
        self.infos.append((message, kwargs))


class DoneTask:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def exception(self):
        if self.error is not None:
            raise self.error
        return self.result


def make_server(monkeypatch):
    opal_server = object.__new__(OpalServer)
    opal_server.broadcaster_uri = "postgres://bad-host:5432/postgres"
    shutdowns = []
    monkeypatch.setattr(
        opal_server,
        "_graceful_shutdown",
        lambda: shutdowns.append("shutdown"),
    )
    return opal_server, shutdowns


def test_logs_broadcast_listener_exception(monkeypatch):
    opal_server, shutdowns = make_server(monkeypatch)
    captured = CapturingLogger()
    monkeypatch.setattr(server_module, "logger", captured)

    opal_server._handle_broadcast_listener_done(
        DoneTask(result=RuntimeError("could not resolve host"))
    )

    assert shutdowns == ["shutdown"]
    assert captured.errors == [
        (
            "Broadcast listener failed; check OPAL server broadcast URI '{uri}': {err}",
            {
                "uri": "postgres://bad-host:5432/postgres",
                "err": "RuntimeError('could not resolve host')",
            },
        )
    ]


def test_logs_cancelled_broadcast_listener(monkeypatch):
    opal_server, shutdowns = make_server(monkeypatch)
    captured = CapturingLogger()
    monkeypatch.setattr(server_module, "logger", captured)

    opal_server._handle_broadcast_listener_done(
        DoneTask(error=asyncio.CancelledError())
    )

    assert shutdowns == ["shutdown"]
    assert captured.infos == [("Broadcast listener task was cancelled", {})]


def test_logs_failure_to_read_listener_result(monkeypatch):
    opal_server, shutdowns = make_server(monkeypatch)
    captured = CapturingLogger()
    monkeypatch.setattr(server_module, "logger", captured)

    opal_server._handle_broadcast_listener_done(
        DoneTask(error=ValueError("task state unavailable"))
    )

    assert shutdowns == ["shutdown"]
    assert captured.errors == [
        (
            "Failed to read broadcast listener task result: {err}",
            {"err": "ValueError('task state unavailable')"},
        )
    ]
