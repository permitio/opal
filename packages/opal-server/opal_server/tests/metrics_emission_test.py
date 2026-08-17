"""The instrumentation this PR emits, and the claims each metric encodes.

Every assertion here is a property an operator reads off a dashboard, so a
regression is silent in production: the metric keeps flowing, it just stops
meaning what the monitor built on it assumes. Each test names the wrong
reading it prevents.
"""
import asyncio

import pytest
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitConcurrencyLimitExceeded,
    _mark_git_op_done,
    _mark_git_op_started,
    run_in_git_executor,
)
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService
from opal_server.server import OpalServer
from starlette.testclient import TestClient


@pytest.fixture
def emitted(monkeypatch):
    """Capture calls through the metrics facade.

    Patched on the module object rather than per-caller: every emitting
    module does `from opal_common.monitoring import metrics`, so they all
    share this one reference.
    """
    calls = {"gauge": [], "increment": []}
    monkeypatch.setattr(
        metrics,
        "gauge",
        lambda metric, value, tags=None: calls["gauge"].append((metric, value, tags)),
    )
    monkeypatch.setattr(
        metrics,
        "increment",
        lambda metric, tags=None: calls["increment"].append((metric, tags)),
    )
    return calls


def _values(calls, name):
    return [(value, tags) for metric, value, tags in calls["gauge"] if metric == name]


def _counts(calls, name):
    return [tags for metric, tags in calls["increment"] if metric == name]


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        await asyncio.sleep(0)
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        await asyncio.sleep(0)
        return list(self._scopes.values())


class FakePubSubEndpoint:
    async def publish(self, topics, data=None):
        pass


def _scope(scope_id, url, poll_updates=True):
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git",
            url=url,
            branch="main",
            auth=NoAuthData(auth_type="none"),
            poll_updates=poll_updates,
        ),
        data={"entries": []},
    )


def test_in_flight_gauge_carries_the_emitting_pid(emitted):
    """Untagged, the pod's 8 workers collapse into one last-write-wins series.

    A reader would then see an arbitrary worker's count and take it for
    the pod's total in-flight git ops — under-reporting zombie
    accumulation by up to a factor of the worker count.
    """
    _mark_git_op_started("metrics-pid")
    try:
        readings = _values(emitted, "opal_server.scopes.git_ops_in_flight")
        assert readings, "starting a git op emitted no in-flight gauge"
        _, tags = readings[-1]
        assert tags and "pid" in tags, f"in-flight gauge is untagged: {tags}"
    finally:
        _mark_git_op_done("metrics-pid")


@pytest.mark.asyncio
async def test_zombie_refusal_is_counted_on_every_refusal(emitted, monkeypatch):
    """The ERROR log latches once per episode; the counter must not.

    `_zombie_cap_logged` deliberately suppresses repeat logs so an outage
    does not bury the one cap-reached line. That makes the log unable to
    answer "how hard, and for how long" — which is exactly what an
    operator needs mid-outage, and what this counter supplies. If it
    latched too, a saturated fleet and a single refused op would look
    identical.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_ZOMBIES", 2)
    _mark_git_op_started("z1")
    _mark_git_op_started("z2")
    try:
        for _ in range(3):
            with pytest.raises(GitConcurrencyLimitExceeded):
                await run_in_git_executor(lambda: 1, timeout=5)

        refusals = _counts(emitted, "opal_server.scopes.git_ops_refused")
        assert len(refusals) == 3, (
            "expected one count per refusal; got "
            f"{len(refusals)} — the counter latches like the log"
        )
    finally:
        _mark_git_op_done("z1")
        _mark_git_op_done("z2")


@pytest.mark.asyncio
async def test_scope_count_is_the_unfiltered_total(emitted, tmp_path):
    """Emitted before the poll-updates filter, so it cannot flap.

    `sync_scopes` is called both unfiltered (boot) and with
    only_poll_updates=True (periodic). Emitting after the filter would
    make one gauge alternate between the fleet total and the
    poll-enabled subset, reading as scopes repeatedly disappearing.
    """
    scopes = [
        _scope("polled", "https://git/a.git", poll_updates=True),
        _scope("static-1", "https://git/b.git", poll_updates=False),
        _scope("static-2", "https://git/c.git", poll_updates=False),
    ]
    service = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository(scopes),
        pubsub_endpoint=FakePubSubEndpoint(),
    )

    await service.sync_scopes(only_poll_updates=True, notify_on_changes=False)

    readings = _values(emitted, "opal_server.scopes.count")
    assert readings, "sync_scopes emitted no scope count"
    assert readings[-1][0] == 3, (
        "scope count reflects the poll-updates filter (got "
        f"{readings[-1][0]}, expected all 3)"
    )


def _build_server():
    return OpalServer(
        init_policy_watcher=False,
        broadcaster_uri=None,
        enable_jwks_endpoint=False,
    )


def _wedge(server):
    """Reader wedged: listeners present, reader task gone."""
    broadcaster = ReconnectingBroadcaster(
        "memory://", notifier=server.pubsub.notifier, channel="test"
    )
    broadcaster._listen_count = 1
    broadcaster._subscription_task = None
    server.pubsub.broadcaster = broadcaster


@pytest.mark.parametrize(
    "wedge, expected_status, expected_gauge",
    [(False, 200, 1), (True, 503, 0)],
)
def test_healthcheck_publishes_what_the_probe_decided(
    emitted, wedge, expected_status, expected_gauge
):
    """The gauge must track the probe's own verdict, in both directions.

    Staging runs no liveness probe, so nothing acts on the 503 — the
    gauge is the only way a wedged reader becomes visible. Asserting the
    status alongside it also pins that publishing the metric did not
    disturb the readiness contract.
    """
    server = _build_server()
    if wedge:
        _wedge(server)
    else:
        server.pubsub.broadcaster = ReconnectingBroadcaster(
            "memory://", notifier=server.pubsub.notifier, channel="test"
        )

    response = TestClient(server.app).get("/healthcheck")

    assert response.status_code == expected_status
    readings = _values(emitted, "opal_server.broadcaster_reader_healthy")
    assert readings, "/healthcheck published no reader-health gauge"
    value, tags = readings[-1]
    assert value == expected_gauge
    assert tags and "pid" in tags, f"reader-health gauge is untagged: {tags}"
