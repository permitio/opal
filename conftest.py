"""Test-session setup shared by every package's tests.

opal_common imports ddtrace in every test process, and ddtrace's tracer is on by default.
Once a span finishes (the topic publisher wraps each publish in one), ddtrace 4 starts its
native trace writer, which keeps retrying a Datadog agent that is not there. Several tests
start servers with multiprocessing, which forks on Linux, and os.fork() then deadlocked in the
parent: ddtrace's before-fork hook waits for the writer thread, which is logging its "failed to
send" through opal_common's loguru intercept, while loguru's own before-fork hook holds the
handler locks. CI's opal-server tests hung in policy_repo_webhook_test.
Tests send no traces, so tracing, telemetry and remote config are off for the test process.
Tests that exercise APM (opal_common/tests/apm_test.py) run it in child interpreters that
set their own environment.

This must run before ddtrace is imported. A rootdir conftest runs before any test module is
collected, but ddtrace's own pytest plugin would import it even earlier, so pytest.ini does not
load that plugin (`-p no:ddtrace`).
"""

import os

for _name, _value in (
    ("DD_TRACE_ENABLED", "false"),
    ("DD_INSTRUMENTATION_TELEMETRY_ENABLED", "false"),
    ("DD_REMOTE_CONFIGURATION_ENABLED", "false"),
):
    os.environ.setdefault(_name, _value)
