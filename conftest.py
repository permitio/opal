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

Every git the tests run, directly or through the code under test, reads no system git config
and an empty global one (GIT_CONFIG_NOSYSTEM, GIT_CONFIG_GLOBAL), so that nothing of the
machine running them comes into play: not its init.defaultBranch, not its fetch.prune, and not
its credential helpers, which could store a test's credentials in the machine's keychain. The
git servers of opal_server's test fixtures, whose env is built afresh, set both themselves. A
test that needs a global config sets GIT_CONFIG_GLOBAL itself; one that needs a system config
unsets GIT_CONFIG_NOSYSTEM as well as setting GIT_CONFIG_SYSTEM, which git ignores while
GIT_CONFIG_NOSYSTEM is set. libgit2 reads none of these variables, so where pygit2 is
installed its global, XDG and system config search paths are an empty directory instead.
"""

import atexit
import os
import shutil
import tempfile

for _name, _value in (
    ("DD_TRACE_ENABLED", "false"),
    ("DD_INSTRUMENTATION_TELEMETRY_ENABLED", "false"),
    ("DD_REMOTE_CONFIGURATION_ENABLED", "false"),
):
    os.environ.setdefault(_name, _value)

_fd, _empty_git_config = tempfile.mkstemp(prefix="opal-tests-", suffix=".gitconfig")
os.close(_fd)
atexit.register(os.remove, _empty_git_config)
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
os.environ["GIT_CONFIG_GLOBAL"] = _empty_git_config
os.environ.pop("GIT_CONFIG_SYSTEM", None)

try:
    import pygit2
except ImportError:  # opal-common and opal-client alone: no libgit2 to isolate
    pass
else:
    _empty_config_dir = tempfile.mkdtemp(prefix="opal-tests-gitconfig-")
    atexit.register(shutil.rmtree, _empty_config_dir, True)
    for _level in (
        pygit2.enums.ConfigLevel.GLOBAL,
        pygit2.enums.ConfigLevel.XDG,
        pygit2.enums.ConfigLevel.SYSTEM,
    ):
        pygit2.settings.search_path[_level] = _empty_config_dir
