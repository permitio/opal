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
from opal_common.monitoring.apm import DropRootPathTraces


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

    It fails on an exception or on any warning ddtrace raises about the
    calls OPAL makes (a removal is announced as a deprecation one major
    ahead).
    """
    code = textwrap.dedent(
        """
        import warnings
        warnings.simplefilter("always")
        with warnings.catch_warnings(record=True) as caught:
            from opal_common.monitoring.apm import configure_apm, fix_ddtrace_logging
            configure_apm(True, "opal-apm-test")
            fix_ddtrace_logging()
        ours = [
            str(w.message) for w in caught
            if "ddtrace" in (w.filename or "") or "ddtrace" in str(w.message)
        ]
        assert not ours, ours
        """
    )
    env = {
        # no agent here: keep the tracer from trying to reach one
        "DD_TRACE_ENABLED": "false",
        "DD_INSTRUMENTATION_TELEMETRY_ENABLED": "false",
        "DD_REMOTE_CONFIGURATION_ENABLED": "false",
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
