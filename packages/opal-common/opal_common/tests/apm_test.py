"""Tests for opal_common.monitoring.apm against the installed ddtrace.

Nothing else in the suite runs this module: APM is off unless
OPAL_ENABLE_DATADOG_APM is set, so a ddtrace major bump that removed an
API OPAL calls would pass every other test. These tests call it.
"""

import os
import subprocess
import sys
import textwrap

import pytest
from ddtrace.trace import Span
from opal_common.monitoring.apm import WEBSOCKET_MESSAGES_ENV, DropRootPathTraces


def _root(**tags):
    span = Span("request", parent_id=None)
    for key, value in tags.items():
        span.set_tag(key, value)
    return span


def _child(root):
    return Span("child", trace_id=root.trace_id, parent_id=root.span_id)


@pytest.mark.parametrize(
    "tags, dropped",
    [
        ({"http.route": "/"}, True),
        ({"http.route": "/data/config"}, False),
        ({"http.url": "http://opal:7002/"}, True),
        ({"http.url": "http://opal:7002/healthcheck"}, False),
        # The rule is the URL's path, not its last character, and a query does not change it.
        ({"http.url": "http://opal:7002/data/"}, False),
        ({"http.url": "http://opal:7002/?x=1"}, True),
        # urlparse raises ValueError on this; the filter fails open and keeps the trace.
        ({"http.url": "http://[::1"}, False),
        ({}, False),
    ],
)
def test_drop_root_path_traces(tags, dropped):
    root = _root(**tags)
    trace = [root, _child(root)]
    result = DropRootPathTraces().process_trace(trace)
    assert (result is None) == dropped
    if not dropped:
        assert result == trace


def test_trace_without_a_root_is_kept():
    orphan = Span("orphan", parent_id=12345)
    orphan.set_tag("http.route", "/")
    assert DropRootPathTraces().process_trace([orphan]) == [orphan]


# The child's environment. Tracing stays on, as in a deployment with APM: with
# DD_TRACE_ENABLED=false, `import ddtrace.auto` leaves FastAPI unpatched, which hides what
# ddtrace-run does. There is no agent here, so the agent URL points at a closed local port; a
# flush fails there and nothing leaves the host. Telemetry and remote config, which have their own
# endpoints, are off.
_CHILD_ENV = {
    "DD_TRACE_AGENT_URL": "http://127.0.0.1:9",
    "DD_INSTRUMENTATION_TELEMETRY_ENABLED": "false",
    "DD_REMOTE_CONFIGURATION_ENABLED": "false",
}

# Records what DropRootPathTraces saw: one (root span's route, every span name, dropped?) per trace.
_SPY = """
from opal_common.monitoring import apm
seen = []
_process = apm.DropRootPathTraces.process_trace
def _spy(self, trace):
    result = _process(self, trace)
    root = next((s for s in trace if s.parent_id is None), None)
    seen.append((root.get_tag("http.route") if root else None, [s.name for s in trace], result is None))
    return result
apm.DropRootPathTraces.process_trace = _spy
"""


def _run_child(code, websocket_messages=None):
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in (WEBSOCKET_MESSAGES_ENV, "DD_TRACE_ENABLED")
    }
    env.update(_CHILD_ENV)
    # The parent's import path, so the child tests this checkout's opal_common even where it is
    # not installed (or an older copy is).
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    if websocket_messages is not None:
        env[WEBSOCKET_MESSAGES_ENV] = websocket_messages
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_configure_apm_runs_on_installed_ddtrace():
    """configure_apm patches integrations process-wide, so it runs in a child
    interpreter.

    The child serves requests through a FastAPI app built after
    configure_apm, so the patched integration code runs, and checks
    that DropRootPathTraces really ran on those traces (dropping `/`,
    keeping `/healthcheck`). It also fails on an exception, on any
    DDTraceDeprecationWarning (ddtrace warns with a stacklevel, so the
    filename is the caller's), or if an integration configure_apm
    enables was not patched: fastapi, aiohttp, loguru, and redis and
    asyncpg where installed (the opal-server legs).
    """
    code = _SPY + textwrap.dedent(
        """
        import importlib, importlib.util, warnings
        warnings.simplefilter("always")
        with warnings.catch_warnings(record=True) as caught:
            from opal_common.monitoring.apm import configure_apm, fix_ddtrace_logging
            configure_apm(True, "opal-apm-test")
            fix_ddtrace_logging()
            import aiohttp  # imported after patch(), so the aiohttp integration is applied too
            import fastapi
            import loguru
            from fastapi.testclient import TestClient
            app = fastapi.FastAPI()
            app.get("/")(lambda: {"ok": True})
            app.get("/healthcheck")(lambda: {"ok": True})
            client = TestClient(app)
            assert client.get("/").status_code == 200
            assert client.get("/healthcheck").status_code == 200
            others = [importlib.import_module(n) for n in ("redis", "asyncpg") if importlib.util.find_spec(n)]
        for module in (fastapi, aiohttp, loguru, *others):
            assert getattr(module, "_datadog_patch", False), f"{module.__name__} was not patched"
        routes = [(route, dropped) for route, _, dropped in seen]
        assert routes == [("/", True), ("/healthcheck", False)], seen
        from ddtrace import DDTraceDeprecationWarning
        ours = [str(w.message) for w in caught if issubclass(w.category, DDTraceDeprecationWarning)]
        assert not ours, ours
        """
    )
    result = _run_child(code)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "prelude", ["", "import ddtrace.auto"], ids=["patch", "ddtrace-run"]
)
@pytest.mark.parametrize(
    ("operator_value", "traced"), [(None, False), ("true", True), ("false", False)]
)
def test_websocket_message_tracing_keeps_the_3x_default(
    prelude, operator_value, traced
):
    """Ddtrace 4 traces every websocket message by default; OPAL's pub/sub runs
    over websockets.

    configure_apm keeps ddtrace 3's default (off) unless the operator
    set DD_TRACE_WEBSOCKET_MESSAGES_ENABLED, and then leaves their
    choice alone. Checked by the spans that reach the trace processor
    for a real websocket session, both with configure_apm patching and
    under ddtrace-run (`import ddtrace.auto`), where FastAPI's
    integration config is read before configure_apm runs.
    """
    code = (
        prelude
        + "\n"
        + _SPY
        + textwrap.dedent(
            """
            import fastapi
            from fastapi.testclient import TestClient
            from opal_common.monitoring.apm import configure_apm
            configure_apm(True, "opal-apm-test")
            app = fastapi.FastAPI()

            @app.websocket("/ws")
            async def ws(websocket: fastapi.WebSocket):
                await websocket.accept()
                for _ in range(3):
                    await websocket.send_text(await websocket.receive_text())
                await websocket.close()

            with TestClient(app).websocket_connect("/ws") as conn:
                for i in range(3):
                    conn.send_text(str(i))
                    assert conn.receive_text() == str(i)
            names = [name for _, trace_names, _ in seen for name in trace_names]
            print(sum(name.startswith("websocket.") for name in names))
            """
        )
    )
    result = _run_child(code, websocket_messages=operator_value)
    assert result.returncode == 0, result.stderr
    message_spans = int(result.stdout.strip().splitlines()[-1])
    assert (message_spans > 0) == traced, f"{message_spans} websocket.* spans"
