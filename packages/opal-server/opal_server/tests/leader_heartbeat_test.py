"""The scopes leader's heartbeat and the per-repository fetch metrics it sends.

The heartbeat file says the leader's event loop still turns, for
/healthz/live and /healthz/started on every worker of the pod; it is
held only by a git command-line op still awaited well past the point
where it should have stopped git. The fetch metrics carry what the old
FETCH_HEAD probe scripts measured, as gauges for monitors instead of a
restart.
"""

import asyncio
import json
import os
import time
from pathlib import Path

import pytest
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server import git_cli, health
from opal_server import git_fetcher as git_fetcher_module
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, cli_ops_past_bound, run_git_cli_op
from opal_server.health import (
    HEARTBEAT_FILE_NAME,
    LeaderHeartbeat,
    emit_repo_fetch_metrics,
)
from opal_server.scopes.task import ScopesPolicyWatcherTask, _SyncPassQueue

pytestmark = pytest.mark.fetch_backend("cli")

_URL = "https://git.example.com/org/policy.git"


@pytest.fixture(autouse=True)
def base(monkeypatch, tmp_path) -> Path:
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _clean_fetcher_state():
    caches = (
        GitPolicyFetcher.repos,
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.repo_locks,
        GitPolicyFetcher.source_backoff,
        GitPolicyFetcher.pending_branches,
        GitPolicyFetcher.branch_attempts,
        GitPolicyFetcher.fetch_failures,
    )
    for cache in caches:
        cache.clear()
    yield
    for cache in caches:
        cache.clear()


@pytest.fixture
def sink(monkeypatch):
    """Every gauge sent, as (name, value, tags)."""
    sent = []
    monkeypatch.setattr(
        metrics,
        "gauge",
        lambda name, value, tags=None: sent.append((name, value, tags)),
    )
    return sent


def _gauges(sent, name):
    return [(value, tags) for metric, value, tags in sent if metric == name]


@pytest.fixture
def logs(monkeypatch):
    """Every line the health module logs, as (level, message)."""
    seen = []
    for level in ("info", "warning", "debug"):
        monkeypatch.setattr(
            health.logger,
            level,
            lambda message, *a, _level=level, **k: seen.append((_level, message)),
        )
    return seen


def _read(base: Path) -> dict:
    return json.loads((base / HEARTBEAT_FILE_NAME).read_text())


def _source(url=_URL, branch="main") -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git", url=url, branch=branch, auth=NoAuthData(auth_type="none")
    )


def _clone(base: Path, source_id: str, fetch_head_age=None) -> Path:
    git_dir = GitPolicyFetcher.base_dir(base) / source_id / ".git"
    git_dir.mkdir(parents=True)
    if fetch_head_age is not None:
        fetch_head = git_dir / "FETCH_HEAD"
        fetch_head.write_text("")
        stamp = time.time() - fetch_head_age
        os.utime(fetch_head, (stamp, stamp))
    return git_dir


# --- the heartbeat file -------------------------------------------------------


def test_a_beat_writes_the_heartbeat_in_base_dir(base):
    before = time.time()
    LeaderHeartbeat().beat(0)
    beat = _read(base)
    assert beat == {
        "pid": os.getpid(),
        "at": beat["at"],
        "last_attempt_at": None,
        "last_attempt": None,
    }
    assert before <= beat["at"] <= time.time()
    assert sorted(p.name for p in base.iterdir()) == [HEARTBEAT_FILE_NAME]


def test_the_next_beat_carries_the_last_attempt(base):
    heartbeat = LeaderHeartbeat()
    heartbeat.note_attempt(False)
    heartbeat.beat(1)
    first = _read(base)
    assert first["last_attempt"] == "failed"
    assert first["last_attempt_at"] <= first["at"]
    heartbeat.note_attempt(True)
    heartbeat.beat(2)
    assert _read(base)["last_attempt"] == "ok"


def test_a_beat_creates_base_dir(base, monkeypatch):
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(base / "new" / "dir"))
    LeaderHeartbeat().beat(1)
    assert _read(base / "new" / "dir")["pid"] == os.getpid()


def test_a_beat_that_cannot_write_warns_once_then_recovers(base, monkeypatch, logs):
    blocked = base / "blocked"
    blocked.write_text("a file where BASE_DIR should be")
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(blocked))
    heartbeat = LeaderHeartbeat()
    for tick in (1, 2, 4):
        heartbeat.beat(tick)
    warnings = [m for level, m in logs if level == "warning"]
    assert len(warnings) == 1, logs
    assert "/healthz/live" in warnings[0]

    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(base))
    heartbeat.beat(5)
    assert _read(base)["pid"] == os.getpid()
    assert any(level == "info" and "heartbeat" in m for level, m in logs), logs
    heartbeat.beat(7)
    assert [m for level, m in logs if level == "warning"] == warnings


def test_a_failed_write_leaves_no_temporary_file(base, monkeypatch):
    def _fail(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(health.os, "replace", _fail)
    LeaderHeartbeat().beat(1)
    assert list(base.iterdir()) == []


def test_each_beat_sends_the_leader_gauge_and_every_third_the_fetch_metrics(
    sink, monkeypatch
):
    emitted = []
    monkeypatch.setattr(health, "emit_repo_fetch_metrics", emitted.append)
    heartbeat = LeaderHeartbeat()
    for tick in range(7):
        heartbeat.beat(tick)
    assert _gauges(sink, "opal_server.scopes.leader") == [(1, None)] * 7
    assert len(emitted) == 3


def test_the_fetch_metrics_failing_does_not_stop_the_heartbeat(base, monkeypatch):
    def _broken(base_dir):
        raise RuntimeError("cannot list the clones")

    monkeypatch.setattr(health, "emit_repo_fetch_metrics", _broken)
    LeaderHeartbeat().beat(0)
    assert _read(base)["pid"] == os.getpid()


@pytest.mark.asyncio
async def test_run_beats_at_once_then_every_interval(base, monkeypatch):
    monkeypatch.setattr(health, "_HEARTBEAT_INTERVAL_SECONDS", 0.02)
    task = asyncio.create_task(LeaderHeartbeat().run())
    try:
        for _ in range(200):
            if (base / HEARTBEAT_FILE_NAME).exists():
                break
            await asyncio.sleep(0.005)
        first = _read(base)["at"]
        await asyncio.sleep(0.1)
        assert _read(base)["at"] > first
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_run_goes_on_after_a_beat_that_raises(base, monkeypatch):
    monkeypatch.setattr(health, "_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    heartbeat = LeaderHeartbeat()
    beat = heartbeat.beat
    calls = []

    def _first_raises(number):
        calls.append(number)
        if len(calls) == 1:
            raise RuntimeError("a bug in one beat")
        beat(number)

    monkeypatch.setattr(heartbeat, "beat", _first_raises)
    task = asyncio.create_task(heartbeat.run())
    try:
        for _ in range(200):
            if (base / HEARTBEAT_FILE_NAME).exists():
                break
            await asyncio.sleep(0.005)
        assert _read(base)["pid"] == os.getpid()
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


# --- a git command-line op past its bound holds the heartbeat -------------------


class _StuckOp:
    """A git command-line op that returns only when released."""

    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def __call__(self, on_gone):
        try:
            await self.release.wait()
        finally:
            on_gone(True)


@pytest.fixture
def tight_bound(monkeypatch):
    """A bound of just the op's timeout: no kill grace, wait or slack."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.0)
    monkeypatch.setattr(git_cli, "KILL_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(git_fetcher_module, "_CLI_OP_BOUND_SLACK_SECONDS", 0.0)


@pytest.mark.asyncio
async def test_the_heartbeat_stops_while_a_cli_op_is_past_its_bound(
    base, tight_bound, logs
):
    heartbeat = LeaderHeartbeat()
    op = _StuckOp()
    running = asyncio.create_task(run_git_cli_op(op, timeout=0.05, busy_key="stuck-0"))
    try:
        await asyncio.sleep(0.01)
        heartbeat.beat(1)
        within = _read(base)["at"]
        await asyncio.sleep(0.1)
        assert cli_ops_past_bound() == 1
        heartbeat.beat(2)
        heartbeat.beat(4)
        assert _read(base)["at"] == within, "the heartbeat moved past a stuck op"
        held = [m for level, m in logs if level == "warning"]
        assert len(held) == 1 and "/healthz/live" in held[0], logs
    finally:
        op.release.set()
        await running
    assert cli_ops_past_bound() == 0
    heartbeat.beat(5)
    assert _read(base)["at"] > within
    assert any(level == "info" for level, _ in logs), logs


@pytest.mark.asyncio
async def test_the_heartbeat_ticks_through_a_slow_op_within_its_bound(base):
    heartbeat = LeaderHeartbeat()
    op = _StuckOp()
    running = asyncio.create_task(run_git_cli_op(op, timeout=60, busy_key="slow-0"))
    try:
        await asyncio.sleep(0.01)
        heartbeat.beat(1)
        first = _read(base)["at"]
        await asyncio.sleep(0.02)
        heartbeat.beat(2)
        assert _read(base)["at"] > first
    finally:
        op.release.set()
        await running


@pytest.mark.asyncio
async def test_the_bound_is_the_timeout_the_kill_grace_the_kill_wait_and_30s(
    monkeypatch,
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 5.0)
    monkeypatch.setattr(git_cli, "KILL_WAIT_SECONDS", 10.0)
    op = _StuckOp()
    started = time.monotonic()
    running = asyncio.create_task(run_git_cli_op(op, timeout=60, busy_key="b-0"))
    try:
        await asyncio.sleep(0.01)
        bound = 60 + 5 + 10 + 30
        assert cli_ops_past_bound(now=started + bound - 0.5) == 0
        assert cli_ops_past_bound(now=time.monotonic() + bound + 0.5) == 1
    finally:
        op.release.set()
        await running
    assert cli_ops_past_bound(now=time.monotonic() + 10_000) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0, -1, float("inf")])
async def test_an_op_with_no_timeout_never_holds_the_heartbeat(timeout):
    op = _StuckOp()
    running = asyncio.create_task(run_git_cli_op(op, timeout=timeout, busy_key="n-0"))
    try:
        await asyncio.sleep(0.01)
        assert cli_ops_past_bound(now=time.monotonic() + 10**9) == 0
    finally:
        op.release.set()
        await running


@pytest.mark.asyncio
async def test_an_op_that_raises_leaves_the_awaited_ops(tight_bound):
    async def _fails(on_gone):
        on_gone(True)
        raise RuntimeError("git failed")

    with pytest.raises(RuntimeError):
        await run_git_cli_op(_fails, timeout=0.01, busy_key="f-0")
    assert cli_ops_past_bound(now=time.monotonic() + 10**6) == 0


@pytest.mark.asyncio
async def test_a_cancelled_op_leaves_the_awaited_ops(tight_bound):
    running = asyncio.create_task(
        run_git_cli_op(_StuckOp(), timeout=0.01, busy_key="c-0")
    )
    await asyncio.sleep(0.01)
    running.cancel()
    await asyncio.gather(running, return_exceptions=True)
    assert cli_ops_past_bound(now=time.monotonic() + 10**6) == 0


# --- the fetch metrics --------------------------------------------------------


def test_fetch_age_equals_now_minus_fetch_head_mtime(base, sink):
    old = f"{'a' * 64}-0"
    new = f"{'b' * 64}-2"
    _clone(base, old, fetch_head_age=123)
    _clone(base, new, fetch_head_age=7)
    emit_repo_fetch_metrics(base)
    ages = sorted(
        (tags["repo"], tags["shard"], value)
        for value, tags in _gauges(sink, "opal_server.scopes.repo_fetch_age_seconds")
    )
    assert [(repo, shard) for repo, shard, _ in ages] == [
        ("a" * 12, "0"),
        ("b" * 12, "2"),
    ]
    assert ages[0][2] == pytest.approx(123, abs=2)
    assert ages[1][2] == pytest.approx(7, abs=2)


def test_a_clone_with_no_fetch_head_sends_no_age_but_its_failures(base, sink):
    source_id = f"{'c' * 64}-0"
    _clone(base, source_id)
    emit_repo_fetch_metrics(base)
    assert _gauges(sink, "opal_server.scopes.repo_fetch_age_seconds") == []
    assert _gauges(sink, "opal_server.scopes.repo_fetch_failures") == [
        (0, {"repo": "c" * 12, "shard": "0"})
    ]


def test_a_fetch_head_from_the_future_reads_as_age_0(base, sink):
    _clone(base, f"{'d' * 64}-0", fetch_head_age=-600)
    emit_repo_fetch_metrics(base)
    assert _gauges(sink, "opal_server.scopes.repo_fetch_age_seconds")[0][0] == 0


def test_only_clone_directories_are_measured(base, sink):
    clones = GitPolicyFetcher.base_dir(base)
    _clone(base, f"{'e' * 64}-0", fetch_head_age=1)
    (clones / ".libgit2-home").mkdir()
    (clones / f".{'e' * 64}-0.lock").write_text("")
    (clones / f".{'e' * 64}-0.known_hosts").write_text("")
    (clones / f"{'f' * 64}-0").write_text("a file named like a clone")
    (clones / f"{'e' * 64}-0.tmp-clone").mkdir()
    emit_repo_fetch_metrics(base)
    repos = {tags["repo"] for _, _, tags in sink}
    assert repos == {"e" * 12}


def test_no_clone_directory_sends_nothing(base, sink):
    emit_repo_fetch_metrics(base)
    assert sink == []


def test_a_source_that_never_cloned_still_reports_its_failures(base, sink):
    GitPolicyFetcher.fetch_failures[f"{'9' * 64}-1"] = 4
    emit_repo_fetch_metrics(base)
    assert _gauges(sink, "opal_server.scopes.repo_fetch_failures") == [
        (4, {"repo": "9" * 12, "shard": "1"})
    ]


def test_the_tags_carry_no_url(base, sink):
    fetcher = GitPolicyFetcher(
        base, "scope", _source("https://u:hunter2@h.example/r.git")
    )
    fetcher._record_source_failure(TimeoutError("timed out"))
    _clone(base, fetcher._source_id, fetch_head_age=1)
    sink.clear()
    emit_repo_fetch_metrics(base)
    assert len(sink) == 2
    for _, _, tags in sink:
        assert set(tags) == {"repo", "shard"}
        assert all(c in "0123456789abcdef" for c in tags["repo"] + tags["shard"])


@pytest.mark.parametrize("backoff_base", [0.0, 30.0])
def test_fetch_failures_count_with_the_backoff_on_or_off(
    base, sink, monkeypatch, backoff_base
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_BACKOFF_BASE_SECONDS", backoff_base
    )
    fetcher = GitPolicyFetcher(base, "scope", _source())
    _clone(base, fetcher._source_id, fetch_head_age=1)
    for _ in range(3):
        fetcher._record_source_failure(TimeoutError("timed out"))
    emit_repo_fetch_metrics(base)
    tags = {"repo": fetcher._source_id[:12], "shard": "0"}
    assert _gauges(sink, "opal_server.scopes.repo_fetch_failures") == [(3, tags)]

    fetcher._clear_source_backoff()
    sink.clear()
    emit_repo_fetch_metrics(base)
    assert _gauges(sink, "opal_server.scopes.repo_fetch_failures") == [(0, tags)]


def test_a_purged_source_drops_its_failure_count(base):
    fetcher = GitPolicyFetcher(base, "scope", _source())
    fetcher._record_source_failure(TimeoutError("timed out"))
    GitPolicyFetcher.forget_source_backoff(fetcher._source_id)
    assert fetcher._source_id not in GitPolicyFetcher.fetch_failures


def test_the_failure_counts_survive_the_pre_fork_reset(base):
    fetcher = GitPolicyFetcher(base, "scope", _source())
    fetcher._record_source_failure(TimeoutError("timed out"))
    GitPolicyFetcher.reset_caches()
    assert GitPolicyFetcher.fetch_failures == {fetcher._source_id: 1}


@pytest.mark.asyncio
async def test_a_real_failing_clone_is_counted_while_the_heartbeat_ticks(
    base, sink, monkeypatch
):
    """A clone git refuses (no such repository) counts one failure, and the
    heartbeat goes on through it."""
    monkeypatch.setattr(health, "_HEARTBEAT_INTERVAL_SECONDS", 0.02)
    missing = base / "no-such-repo.git"
    fetcher = GitPolicyFetcher(base, "scope", _source(url=missing.as_uri()))
    beating = asyncio.create_task(LeaderHeartbeat().run())
    try:
        await asyncio.sleep(0.01)
        first = _read(base)["at"]
        for _ in range(2):
            await fetcher.fetch_and_notify_on_changes(force_fetch=True)
        await asyncio.sleep(0.05)
        assert _read(base)["at"] > first
    finally:
        beating.cancel()
        await asyncio.gather(beating, return_exceptions=True)
    assert GitPolicyFetcher.fetch_failures == {fetcher._source_id: 2}
    sink.clear()
    emit_repo_fetch_metrics(base)
    assert _gauges(sink, "opal_server.scopes.repo_fetch_failures") == [
        (2, {"repo": fetcher._source_id[:12], "shard": "0"})
    ]


# --- the leader task ----------------------------------------------------------


class _Service:
    def __init__(self, fail: bool) -> None:
        self._fail = fail

    async def sync_scopes(self, *args, **kwargs):
        if self._fail:
            raise RuntimeError("the scope store is down")

    async def sync_scope(self, *args, **kwargs):
        if self._fail:
            raise RuntimeError("the scope store is down")
        return None


class _Notifier:
    def gen_subscriber_id(self):
        return "sub"

    async def subscribe(self, *args, **kwargs):
        return None

    async def unsubscribe(self, *args, **kwargs):
        return None


class _Endpoint:
    notifier = _Notifier()
    broadcaster = None


class _Purger:
    async def handle(self, *args, **kwargs):
        return None

    def signal_stop(self):
        return None

    async def stop(self):
        return None


def _task(fail=False) -> ScopesPolicyWatcherTask:
    task = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    task._service = _Service(fail)
    task._purger = _Purger()
    task._pubsub_endpoint = _Endpoint()
    task._tasks = []
    task._webhook_tasks = []
    task._should_stop = None
    task._purger_sub_id = None
    task._remove_gap_listener = None
    task._passes = _SyncPassQueue(task._run_pass)
    return task


@pytest.fixture
def heartbeat(monkeypatch) -> LeaderHeartbeat:
    """The process's heartbeat, fresh for the test."""
    fresh = LeaderHeartbeat()
    monkeypatch.setattr(health, "leader_heartbeat", fresh)
    return fresh


@pytest.mark.asyncio
@pytest.mark.parametrize("fail, outcome", [(False, "ok"), (True, "failed")])
async def test_a_sync_pass_notes_its_attempt(base, heartbeat, fail, outcome):
    await _task(fail)._passes.request(only_poll_updates=False, honor_backoff=True)
    heartbeat.beat(1)
    assert _read(base)["last_attempt"] == outcome


@pytest.mark.asyncio
async def test_a_scope_refresh_notes_its_attempt(base, heartbeat):
    await _task().trigger(topic=None, data={"scope_id": "s1"})
    heartbeat.beat(1)
    assert _read(base)["last_attempt"] == "ok"
    with pytest.raises(RuntimeError):
        await _task(fail=True).trigger(topic=None, data={"scope_id": "s1"})
    heartbeat.beat(2)
    assert _read(base)["last_attempt"] == "failed"


@pytest.mark.asyncio
async def test_an_invalid_refresh_is_no_attempt(base, heartbeat):
    await _task().trigger(topic=None, data={"no_scope_id": "s1"})
    heartbeat.beat(1)
    assert _read(base)["last_attempt"] is None


@pytest.mark.asyncio
async def test_the_periodic_pass_no_longer_sends_the_leader_gauge(sink, monkeypatch):
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0.001)
    task = _task()
    polling = asyncio.create_task(task._periodic_polling())
    try:
        await asyncio.sleep(0.05)
    finally:
        polling.cancel()
        await asyncio.gather(polling, return_exceptions=True)
    assert _gauges(sink, "opal_server.scopes.leader") == []
