"""The argv OPAL builds must be accepted by the REAL opa binary.

Asserting that ``get_cli_options_dict()`` returns strings is necessary but not
sufficient: these enums are ``str`` mixins, so a broken value satisfies both
``isinstance(v, str)`` and ``v == "off"``. The only assertion that cannot be
fooled is handing the argv to ``opa`` and seeing whether it parses.

This is the check that would have caught the inline-OPA regression directly.
It renders differently per python version (``Enum.__format__`` changed in 3.11)
and the CI unit matrix already runs 3.10 / 3.11 / 3.12, so this test inherits
the version matrix for free - which the 3.10-only images and E2E leg do not.

The binary is located from, in order:
  OPAL_TEST_OPA_BINARY, OPAL_INLINE_OPA_EXEC_PATH, then ``opa`` on PATH.
If none is present the tests SKIP with that reason rather than passing: a
missing instrument is not evidence that the argv is correct.
"""

import os
import shutil
import subprocess
import sys

import pytest
from opal_client.engine.options import (
    AuthenticationScheme,
    AuthorizationScheme,
    LogLevel,
    OpaServerOptions,
)
from opal_client.engine.runner import OpaRunner

# A port nothing else in the suite binds; the server is killed immediately.
PROBE_ADDR = "127.0.0.1:18181"


def _find_opa():
    for env_var in ("OPAL_TEST_OPA_BINARY", "OPAL_INLINE_OPA_EXEC_PATH"):
        candidate = os.environ.get(env_var)
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("opa")


OPA_BINARY = _find_opa()

requires_opa = pytest.mark.skipif(
    OPA_BINARY is None,
    reason=(
        "no opa binary found - set OPAL_TEST_OPA_BINARY, OPAL_INLINE_OPA_EXEC_PATH, "
        "or put `opa` on PATH. Skipped rather than passed: without the binary this "
        "asserts nothing about whether OPA accepts the flags."
    ),
)


def _run_opa(args) -> str:
    """Start opa with these args and return its first output.

    A flag error makes opa exit immediately; a good argv starts the
    server, so the call is bounded by a timeout and the process killed
    either way.
    """
    proc = subprocess.Popen(
        [OPA_BINARY] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        out, _ = proc.communicate(timeout=4)
    except subprocess.TimeoutExpired:
        # still running == it accepted the flags and bound the port
        proc.kill()
        out, _ = proc.communicate()
    return out or ""


def _argv_for(options: OpaServerOptions):
    """The production argv builder, not a replica of it."""
    args = OpaRunner(options=options).get_arguments()
    # point the probe at a port the suite does not otherwise use
    return [a if not a.startswith("--addr=") else f"--addr={PROBE_ADDR}" for a in args]


OPTION_CASES = {
    # the default production path: INLINE_OPA_CONFIG resolves to this
    "all_defaults": OpaServerOptions.model_validate({}),
    "constructed_empty": OpaServerOptions(),
    "explicit_log_level_str": OpaServerOptions(log_level="debug"),
    "explicit_log_level_enum": OpaServerOptions(log_level=LogLevel.debug),
    "explicit_authn_enum": OpaServerOptions(authentication=AuthenticationScheme.off),
    "explicit_authz_enum": OpaServerOptions(authorization=AuthorizationScheme.off),
    "explicit_authz_basic": OpaServerOptions(authorization=AuthorizationScheme.basic),
}


@requires_opa
@pytest.mark.parametrize("name", sorted(OPTION_CASES))
def test_real_opa_accepts_generated_argv(name):
    """Opa must not reject any flag OPAL generates."""
    argv = _argv_for(OPTION_CASES[name])

    output = _run_opa(argv)

    assert "invalid argument" not in output, (
        f"\nopa rejected a flag OPAL generated (case: {name}, python "
        f"{sys.version_info.major}.{sys.version_info.minor}).\n"
        f"  argv: {argv}\n"
        f"  opa:  {output.strip().splitlines()[0] if output.strip() else '<no output>'}\n\n"
        "An enum member surviving model_dump() renders as 'ClassName.member' in "
        "the f-string runner.py builds argv with, on python 3.11+."
    )


@requires_opa
def test_real_opa_rejects_the_regression_argv():
    """The control: prove the probe can actually tell the two apart.

    Without this, a probe that never detects anything would make every test
    above pass vacuously.
    """
    broken = [
        "run",
        "--server",
        f"--addr={PROBE_ADDR}",
        "--authentication=AuthenticationScheme.off",
        "--authorization=AuthorizationScheme.off",
        "--log-level=LogLevel.info",
    ]

    output = _run_opa(broken)

    assert "invalid argument" in output, (
        "the probe did not detect a known-bad argv, so the assertions above "
        f"prove nothing. opa said: {output.strip()[:200]!r}"
    )


@pytest.mark.parametrize("name", sorted(OPTION_CASES))
def test_argv_renders_without_enum_repr(name):
    """Version-sensitive guard that needs no binary.

    ``Enum.__format__`` changed in 3.11, so this is the assertion that varies
    across the CI matrix. It runs everywhere, binary or not.
    """
    argv = _argv_for(OPTION_CASES[name])

    for arg in argv:
        _, _, value = arg.partition("=")
        assert "Scheme." not in value and "LogLevel." not in value, (
            f"enum repr leaked into argv on python {sys.version_info.major}."
            f"{sys.version_info.minor}: {arg!r} (case: {name})"
        )
