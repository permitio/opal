"""The inline engine's command line is logged with credential values masked,
while the process still receives them."""

import asyncio

import pytest
from opal_client.config import opal_client_config
from opal_client.engine.options import CedarServerOptions
from opal_client.engine.runner import CedarRunner, redact_engine_arguments
from opal_common.tests.redaction_fixtures import capture_logs
from tenacity import stop_after_attempt

FAKE_KEY = "FAKE-KEY-123"


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (["-a", FAKE_KEY, "--addr", "0.0.0.0"], ["-a", "***", "--addr", "0.0.0.0"]),
        (["--authentication", FAKE_KEY], ["--authentication", "***"]),
        (
            ["--api-token", FAKE_KEY, "--port", "1"],
            ["--api-token", "***", "--port", "1"],
        ),
        (["--db-password=" + FAKE_KEY], ["--db-password=***"]),
        (["-a"], ["-a"]),
        # OPA's flags: a scheme name, a key *path* and file arguments stay readable
        (
            [
                "run",
                "--authentication=token",
                "--tls-private-key-file=/k.pem",
                "p.rego",
            ],
            [
                "run",
                "--authentication=token",
                "--tls-private-key-file=/k.pem",
                "p.rego",
            ],
        ),
    ],
)
def test_redact_engine_arguments(arguments, expected):
    assert redact_engine_arguments(arguments) == expected


class _ProcessStarted(Exception):
    pass


@pytest.mark.asyncio
async def test_engine_start_log_masks_cedar_token(monkeypatch):
    options = CedarServerOptions(authentication="token", authentication_token=FAKE_KEY)
    runner = CedarRunner(options=options)
    monkeypatch.setattr(
        opal_client_config, "INLINE_CEDAR_EXEC_PATH", "/bin/cedar-agent"
    )
    started_with = []

    async def fake_exec(*argv, **kwargs):
        started_with.extend(argv)
        raise _ProcessStarted()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    run_once = runner._run_process_until_terminated.retry_with(
        stop=stop_after_attempt(1), reraise=True
    )
    with capture_logs() as logs:
        with pytest.raises(_ProcessStarted):
            await run_once(runner)

    assert (
        "Running policy engine inline: /bin/cedar-agent -a *** --addr" in logs.combined
    )
    assert FAKE_KEY not in logs.combined
    assert started_with[:3] == ["/bin/cedar-agent", "-a", FAKE_KEY]
