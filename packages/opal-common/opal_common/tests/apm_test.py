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


def test_configure_apm_runs_on_installed_ddtrace():
    """configure_apm patches integrations process-wide, so it runs in a child
    interpreter.

    The child then builds a FastAPI app and serves requests through it,
    so the patched integration code runs, not only its registration. It
    fails on an exception, on any DDTraceDeprecationWarning (a removal
    is announced as a deprecation one major ahead; ddtrace warns with a
    stacklevel, so the filename is the caller's, not ddtrace's), or if
    FastAPI was not patched.
    """
    code = textwrap.dedent(
        """
        import warnings
        warnings.simplefilter("always")
        from ddtrace import DDTraceDeprecationWarning
        with warnings.catch_warnings(record=True) as caught:
            from opal_common.monitoring.apm import configure_apm, fix_ddtrace_logging
            configure_apm(True, "opal-apm-test")
            fix_ddtrace_logging()
            import aiohttp  # imported after patch(), so the aiohttp integration is applied too
            import fastapi
            from fastapi.testclient import TestClient
            app = fastapi.FastAPI()
            app.get("/")(lambda: {"ok": True})
            app.get("/healthcheck")(lambda: {"ok": True})
            client = TestClient(app)
            assert client.get("/").status_code == 200
            assert client.get("/healthcheck").status_code == 200
        assert getattr(fastapi, "_datadog_patch", False), "FastAPI was not patched"
        assert getattr(aiohttp, "_datadog_patch", False), "aiohttp was not patched"
        ours = [str(w.message) for w in caught if issubclass(w.category, DDTraceDeprecationWarning)]
        assert not ours, ours
        """
    )
    env = {
        # No agent here. configure_apm's tracer.configure() turns the tracer back on whatever
        # DD_TRACE_ENABLED says, and the requests below finish spans, so the agent URL points at
        # a closed local port: a flush fails there and nothing leaves the host. Telemetry and
        # remote config, which have their own endpoints, are off.
        "DD_TRACE_AGENT_URL": "http://127.0.0.1:9",
        "DD_TRACE_ENABLED": "false",
        "DD_INSTRUMENTATION_TELEMETRY_ENABLED": "false",
        "DD_REMOTE_CONFIGURATION_ENABLED": "false",
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        # The parent's import path, so the child tests this checkout's opal_common even where
        # it is not installed (or an older copy is).
        env={**os.environ, **env, "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("operator_value", "expected"), [(None, False), ("true", True), ("false", False)]
)
def test_websocket_message_tracing_keeps_the_3x_default(operator_value, expected):
    """Ddtrace 4 traces every websocket message by default; OPAL's pub/sub runs
    over websockets.

    configure_apm keeps ddtrace 3's default (off) unless the operator
    set DD_TRACE_WEBSOCKET_MESSAGES_ENABLED, and then leaves their
    choice alone.
    """
    code = textwrap.dedent(
        """
        import fastapi  # imported first, as opal-server does, so patch() applies the ASGI integration now
        from ddtrace import config
        from opal_common.monitoring.apm import configure_apm
        configure_apm(True, "opal-apm-test")
        print(config.asgi.trace_asgi_websocket_messages)
        """
    )
    env = {k: v for k, v in os.environ.items() if k != WEBSOCKET_MESSAGES_ENV}
    env.update(
        {
            "DD_TRACE_AGENT_URL": "http://127.0.0.1:9",
            "DD_TRACE_ENABLED": "false",
            "DD_INSTRUMENTATION_TELEMETRY_ENABLED": "false",
            "DD_REMOTE_CONFIGURATION_ENABLED": "false",
            "PYTHONPATH": os.pathsep.join(sys.path),
        }
    )
    if operator_value is not None:
        env[WEBSOCKET_MESSAGES_ENV] = operator_value
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == str(expected)
