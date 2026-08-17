"""Per-source failure backoff: a repo that keeps failing must stop being
retried on every periodic pass, while an operator's explicit refresh still gets
through immediately.

The production shape this encodes: 19 fast-failing sources produced 4,579 clone
attempts in three hours on prod-us, because nothing recorded a failure — every
pass re-attempted every dead source, and every duplicate scope sharing that
source re-attempted it too (one repo with ~56 scopes accounted for 2,410 of
them). Each test below names, in its docstring, the single-line mutation it
catches; every one of them was run against the implementation.
"""
import asyncio
import datetime
import math
import os
import time

import pygit2
import pytest
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, SourceBackoff, git_op_in_flight
from opal_server.scopes.purge import purge_local_memory
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService

# The default POLICY_REFRESH_INTERVAL is 0 (polling disabled); prod runs 60.
# Tests that assert on the schedule pin it explicitly so the fallback and the
# configured base are each covered by a test that names which one it is.
_BASE = 60.0


@pytest.fixture(autouse=True)
def _reset_class_state(monkeypatch):
    """source_backoff is process-global class state — leaking an entry between
    tests would make a later test pass for the wrong reason."""
    for d in (
        GitPolicyFetcher.repos,
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.repo_locks,
        GitPolicyFetcher.source_backoff,
    ):
        d.clear()
    # Pin the schedule inputs: the suite must not depend on the ambient
    # OPAL_POLICY_REFRESH_INTERVAL of whatever shell runs it.
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", int(_BASE))
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_BACKOFF_MAX_SECONDS", 3600.0)
    yield
    for d in (
        GitPolicyFetcher.repos,
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.repo_locks,
        GitPolicyFetcher.source_backoff,
    ):
        d.clear()


@pytest.fixture
def no_jitter(monkeypatch):
    """Pin the ±20% jitter to 1.0 so delays are exact.

    Patched on the module seam rather than on ``random``: the seam is what the
    envelope test below proves is really wired up.
    """
    monkeypatch.setattr("opal_server.git_fetcher._jittered", lambda delay: delay)


@pytest.fixture
def emitted(monkeypatch):
    """Capture calls through the metrics facade (same pattern as
    metrics_emission_test)."""
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


def _gauges(calls, name):
    return [(value, tags) for metric, value, tags in calls["gauge"] if metric == name]


def _counts(calls, name):
    return [tags for metric, tags in calls["increment"] if metric == name]


def _source(url, branch="main"):
    # poll_updates=True so sync_scopes(only_poll_updates=True) — the periodic
    # pass, the caller this whole feature is about — actually sees the scope.
    return GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch=branch,
        auth=NoAuthData(auth_type="none"),
        poll_updates=True,
    )


def _fetcher(tmp_path, scope_id="s1", url="https://git/backoff.git"):
    return GitPolicyFetcher(base_dir=tmp_path, scope_id=scope_id, source=_source(url))


class _ReachedGitWork(Exception):
    """Raised from a stubbed _discover_repository to prove execution got past
    the backoff check (it is the first thing the method does after it)."""


def _tripwire(fetcher, monkeypatch):
    """Make any attempt to do real work for this source raise, loudly."""

    def _boom(_path):
        raise _ReachedGitWork

    monkeypatch.setattr(fetcher, "_discover_repository", _boom)
    return fetcher


def _fail_clone_with(monkeypatch, exc):
    """Replace the one blocking git call with a failing stand-in.

    Everything above it — fetch_and_notify_on_changes, the lock, the
    liveness check, _clone's except clause — is the real code path.
    """
    calls = []

    async def _fake(func, *args, timeout=None, busy_key=None, **kwargs):
        calls.append(busy_key)
        raise exc

    monkeypatch.setattr("opal_server.git_fetcher.run_in_git_executor", _fake)
    return calls


class _FakeRepo:
    """Stands in for the pygit2 Repository a successful clone returns."""

    def free(self):
        return None


def _succeed_clone(monkeypatch):
    calls = []

    async def _fake(func, *args, timeout=None, busy_key=None, **kwargs):
        calls.append(busy_key)
        return _FakeRepo()

    monkeypatch.setattr("opal_server.git_fetcher.run_in_git_executor", _fake)

    async def _no_notify(self, repo):
        return None

    monkeypatch.setattr(GitPolicyFetcher, "_notify_on_changes", _no_notify)
    return calls


def _capture_logs(level):
    records = []
    sink = logger.add(lambda m: records.append(str(m)), level=level)
    return records, sink


# --------------------------------------------------------------------------
# The schedule
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_clone_records_one_base_interval(
    tmp_path, monkeypatch, no_jitter
):
    """Mutation: delete the ``_record_source_failure`` call from ``_clone``'s
    ``except (pygit2.GitError, TimeoutError)`` — nothing is ever recorded, so
    nothing is ever skipped and the whole feature is inert while every other
    test that seeds an entry by hand still passes."""
    fetcher = _fetcher(tmp_path)
    _fail_clone_with(monkeypatch, pygit2.GitError("remote unauthorized"))

    before = time.monotonic()
    await fetcher.fetch_and_notify_on_changes()
    after = time.monotonic()

    entry = GitPolicyFetcher.source_backoff[fetcher._source_id]
    assert entry.consecutive_failures == 1
    assert before + _BASE <= entry.next_attempt_at <= after + _BASE
    assert "unauthorized" in entry.last_error


@pytest.mark.asyncio
async def test_consecutive_failures_double_the_delay(tmp_path, monkeypatch, no_jitter):
    """Mutation: ``base * 2 ** (n - 1)`` -> ``base`` (or ``base * n``). A flat
    or linear schedule keeps hammering a repo that has been dead for hours,
    which is the cost this key exists to bound — and the first-failure test
    above passes either way, because n=1 is identical in all three."""
    fetcher = _fetcher(tmp_path)
    _fail_clone_with(monkeypatch, pygit2.GitError("remote unauthorized"))

    delays = []
    for _ in range(4):
        before = time.monotonic()
        await fetcher.fetch_and_notify_on_changes()
        delays.append(
            GitPolicyFetcher.source_backoff[fetcher._source_id].next_attempt_at - before
        )

    assert GitPolicyFetcher.source_backoff[fetcher._source_id].consecutive_failures == 4
    # 60, 120, 240, 480 — assert the ratio, not the absolute float.
    for i, expected in enumerate((1, 2, 4, 8)):
        assert delays[i] == pytest.approx(_BASE * expected, abs=0.5), delays


@pytest.mark.asyncio
async def test_the_delay_is_capped(tmp_path, monkeypatch, no_jitter):
    """Mutation: drop the ``min(..., cap)`` — doubling from 60s reaches a
    ~19-day wait after 15 failures, so a repo fixed on day two is never retried
    and the operator sees a scope that simply stopped syncing."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_BACKOFF_MAX_SECONDS", 300.0)
    fetcher = _fetcher(tmp_path)
    _fail_clone_with(monkeypatch, pygit2.GitError("remote unauthorized"))

    for _ in range(12):
        before = time.monotonic()
        await fetcher.fetch_and_notify_on_changes()
    delay = GitPolicyFetcher.source_backoff[fetcher._source_id].next_attempt_at - before

    assert delay == pytest.approx(300.0, abs=0.5)


@pytest.mark.asyncio
async def test_a_source_failing_for_days_does_not_overflow(
    tmp_path, monkeypatch, no_jitter
):
    """Mutation: compute the doubling as ``base * 2 ** (n - 1)`` with an
    unclamped integer exponent. A source failing once a minute reaches n>1000
    in under a day, and ``60.0 * 2**1024`` raises OverflowError from inside the
    except clause that is handling the git failure — turning a backed-off repo
    into an unhandled exception on the sync pass."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_BACKOFF_MAX_SECONDS", 3600.0)
    fetcher = _fetcher(tmp_path)
    _fail_clone_with(monkeypatch, pygit2.GitError("remote unauthorized"))

    # Seed a pathological failure count directly: driving 2,000 real passes
    # would take minutes and prove the same arithmetic.
    GitPolicyFetcher.source_backoff[fetcher._source_id] = SourceBackoff(
        consecutive_failures=2000,
        next_attempt_at=time.monotonic() - 1,
        last_error="seeded",
    )

    before = time.monotonic()
    await fetcher.fetch_and_notify_on_changes()  # must not raise

    entry = GitPolicyFetcher.source_backoff[fetcher._source_id]
    assert entry.consecutive_failures == 2001
    assert entry.next_attempt_at - before == pytest.approx(3600.0, abs=0.5)


@pytest.mark.asyncio
async def test_jitter_stays_inside_its_envelope_and_actually_varies(
    tmp_path, monkeypatch
):
    """Mutation (two of them): ``_jittered`` -> ``return delay`` removes the
    spread that keeps a fleet's dead sources from re-attempting in lockstep
    (caught by the "varies" half); widening it to ``uniform(0, 5)`` makes the
    schedule unrecognisable (caught by the envelope half).

    No ``no_jitter``
    fixture here on purpose — this is the one test that runs the real seam.
    """
    fetcher = _fetcher(tmp_path)
    _fail_clone_with(monkeypatch, pygit2.GitError("remote unauthorized"))

    samples = []
    for _ in range(60):
        GitPolicyFetcher.source_backoff.clear()
        before = time.monotonic()
        await fetcher.fetch_and_notify_on_changes()
        samples.append(
            GitPolicyFetcher.source_backoff[fetcher._source_id].next_attempt_at - before
        )

    assert all(0.8 * _BASE <= s <= 1.2 * _BASE + 0.5 for s in samples), samples
    # Spread in SECONDS, not merely "the values differ": every sample is derived
    # from a time.monotonic() reading, so scheduling noise alone makes them all
    # distinct and a `len(set(...)) > 1` assertion passes with the jitter removed
    # entirely. A live ±20% seam spans ~24s of the 60s base; noise spans
    # microseconds.
    assert max(samples) - min(samples) > 1.0, (
        f"jitter spread was {max(samples) - min(samples):.6f}s — the seam is "
        f"returning the delay unchanged"
    )


@pytest.mark.asyncio
async def test_the_base_falls_back_when_polling_is_disabled(
    tmp_path, monkeypatch, no_jitter
):
    """Mutation: ``base = POLICY_REFRESH_INTERVAL if > 0 else 60.0`` ->
    ``base = POLICY_REFRESH_INTERVAL``. The shipped default is 0, so every
    delay becomes 0 and the entry is created already expired — recorded,
    reported, and skipping nothing."""
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0)
    fetcher = _fetcher(tmp_path)
    _fail_clone_with(monkeypatch, pygit2.GitError("remote unauthorized"))

    before = time.monotonic()
    await fetcher.fetch_and_notify_on_changes()
    delay = GitPolicyFetcher.source_backoff[fetcher._source_id].next_attempt_at - before

    assert delay == pytest.approx(60.0, abs=0.5)


# --------------------------------------------------------------------------
# The decision point
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pass_originated_sync_skips_a_backed_off_source(
    tmp_path, monkeypatch, emitted
):
    """Mutation: ``if honor_backoff and self._backoff_entry() is not None`` ->
    ``if False`` (or dropping the early return). The state is still recorded
    and the gauge still moves, so every schedule test above passes, while the
    pass keeps attempting the dead repo exactly as often as before."""
    fetcher = _tripwire(_fetcher(tmp_path), monkeypatch)
    GitPolicyFetcher.source_backoff[fetcher._source_id] = SourceBackoff(
        consecutive_failures=3,
        next_attempt_at=time.monotonic() + 300,
        last_error="boom",
    )
    records, sink = _capture_logs("DEBUG")
    try:
        await fetcher.fetch_and_notify_on_changes(honor_backoff=True)
    finally:
        logger.remove(sink)

    assert _counts(emitted, "opal_server.scopes.git_op_skipped") == [
        {"reason": "backoff"}
    ]
    assert any("backing off" in r.lower() or "backoff" in r.lower() for r in records)


@pytest.mark.asyncio
async def test_the_skip_happens_before_the_source_lock_is_taken(tmp_path, monkeypatch):
    """Mutation: move the backoff check inside ``async with lock_source(...)``.
    A skipped source would then queue behind the very clone that is hung on
    that source's lock — the phase-2 duplicate storm this change exists to
    collapse would serialise instead of vanishing, and the pass would still
    take the full SCOPES_GIT_FETCH_TIMEOUT per dead repo."""
    fetcher = _tripwire(_fetcher(tmp_path), monkeypatch)
    GitPolicyFetcher.source_backoff[fetcher._source_id] = SourceBackoff(
        consecutive_failures=1,
        next_attempt_at=time.monotonic() + 300,
        last_error="boom",
    )

    await fetcher.fetch_and_notify_on_changes(honor_backoff=True)

    assert (
        GitPolicyFetcher.repo_locks == {}
    ), "lock_source was entered for a source that is in backoff"


@pytest.mark.asyncio
async def test_the_skip_expires(tmp_path, monkeypatch):
    """Mutation: ``time.monotonic() < entry.next_attempt_at`` -> ``True``. A
    source that fails once is then never retried for the life of the process,
    which is strictly worse than the bug being fixed."""
    fetcher = _tripwire(_fetcher(tmp_path), monkeypatch)
    GitPolicyFetcher.source_backoff[fetcher._source_id] = SourceBackoff(
        consecutive_failures=1,
        next_attempt_at=time.monotonic() - 0.01,
        last_error="boom",
    )

    with pytest.raises(_ReachedGitWork):
        await fetcher.fetch_and_notify_on_changes(honor_backoff=True)


@pytest.mark.asyncio
async def test_an_explicit_sync_ignores_the_backoff(tmp_path, monkeypatch, emitted):
    """Mutation: default ``honor_backoff`` to True on
    ``fetch_and_notify_on_changes``. A customer who has just fixed revoked
    credentials and hits POST /scopes/{id}/refresh would be told 200 OK and
    then wait up to an hour for anything to happen."""
    fetcher = _tripwire(_fetcher(tmp_path), monkeypatch)
    GitPolicyFetcher.source_backoff[fetcher._source_id] = SourceBackoff(
        consecutive_failures=9,
        next_attempt_at=time.monotonic() + 3600,
        last_error="boom",
    )

    with pytest.raises(_ReachedGitWork):
        await fetcher.fetch_and_notify_on_changes()

    assert _counts(emitted, "opal_server.scopes.git_op_skipped") == []


# --------------------------------------------------------------------------
# Recovery
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_successful_clone_clears_the_backoff(tmp_path, monkeypatch, emitted):
    """Mutation: delete the ``_clear_source_backoff()`` call from ``_clone``'s
    success branch. A source that recovers keeps its escalating delay forever:
    the next failure resumes from n=9 rather than n=1, and the recovered source
    is still counted in the sources_in_backoff gauge."""
    fetcher = _fetcher(tmp_path)
    GitPolicyFetcher.source_backoff[fetcher._source_id] = SourceBackoff(
        consecutive_failures=9,
        next_attempt_at=time.monotonic() + 3600,
        last_error="boom",
    )
    _succeed_clone(monkeypatch)
    records, sink = _capture_logs("INFO")
    try:
        await fetcher.fetch_and_notify_on_changes()
    finally:
        logger.remove(sink)

    assert fetcher._source_id not in GitPolicyFetcher.source_backoff
    assert any("recovered after 9" in r for r in records), records
    assert _gauges(emitted, "opal_server.scopes.sources_in_backoff")[-1][0] == 0


@pytest.mark.asyncio
async def test_a_successful_fetch_clears_the_backoff(tmp_path, monkeypatch):
    """Mutation: clear only on the clone path, not on the fetch path. An
    already-cloned repo whose creds were fixed keeps its backoff for the life
    of the process — the fetch path is the one that recovers in production,
    since the clone dir survives the outage."""
    fetcher = _fetcher(tmp_path)
    GitPolicyFetcher.source_backoff[fetcher._source_id] = SourceBackoff(
        consecutive_failures=4,
        next_attempt_at=time.monotonic() + 3600,
        last_error="boom",
    )

    class _OkRemote:
        def fetch(self, *args, **kwargs):
            return None

    class _RepoWithRemote:
        remotes = {"origin": _OkRemote()}

    monkeypatch.setattr(fetcher, "_discover_repository", lambda path: True)
    monkeypatch.setattr(fetcher, "_get_valid_repo", lambda: _RepoWithRemote())

    async def _no_notify(repo):
        return None

    monkeypatch.setattr(fetcher, "_notify_on_changes", _no_notify)

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert fetcher._source_id not in GitPolicyFetcher.source_backoff


@pytest.mark.asyncio
async def test_a_failing_fetch_is_recorded_too(tmp_path, monkeypatch, emitted):
    """Mutation: record on the clone path only. Revoked credentials on a repo
    that is ALREADY cloned fail in ``remote.fetch`` with a GitError, never
    reaching ``_clone`` — which is most of the fast-fail population in prod,
    since the clone dir outlives the outage. Also pins that the GitError keeps
    propagating (sync_scope logs it), rather than being swallowed here."""
    fetcher = _fetcher(tmp_path)

    class _FailingRemote:
        def fetch(self, *args, **kwargs):
            raise pygit2.GitError("authentication required")

    class _RepoWithRemote:
        remotes = {"origin": _FailingRemote()}

    monkeypatch.setattr(fetcher, "_discover_repository", lambda path: True)
    monkeypatch.setattr(fetcher, "_get_valid_repo", lambda: _RepoWithRemote())

    with pytest.raises(pygit2.GitError):
        await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert GitPolicyFetcher.source_backoff[fetcher._source_id].consecutive_failures == 1
    assert {"op": "fetch", "reason": "git_error"} in _counts(
        emitted, "opal_server.scopes.git_op_failures"
    )


@pytest.mark.asyncio
async def test_a_timed_out_git_op_is_recorded_as_a_failure(tmp_path, monkeypatch):
    """Mutation: drop TimeoutError from the recorded set (record only
    GitError). The firewalled hosts are exactly the TimeoutError population —
    132s of SYN-drop per attempt — so the expensive half of the prod problem
    would keep being retried every pass.

    Drives a real hanging call through run_in_git_executor rather than raising
    TimeoutError directly, so the timeout wiring is part of what is asserted.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.2)
    # Its own URL: the abandoned call keeps this source marked in-flight until
    # it returns, which would make any later test on the same source_id take
    # the in-flight skip instead of the path it means to exercise.
    fetcher = _fetcher(tmp_path, url="https://git/hangs.git")

    def _hang(*args, **kwargs):
        time.sleep(0.5)  # well above the 0.2s timeout, short enough to reap here

    monkeypatch.setattr("opal_server.git_fetcher.clone_repository", _hang)

    await fetcher.fetch_and_notify_on_changes()

    entry = GitPolicyFetcher.source_backoff[fetcher._source_id]
    assert entry.consecutive_failures == 1
    assert "TimeoutError" in entry.last_error

    # Reap the abandoned daemon thread before the loop closes, so its late
    # future callback does not fire against a dead loop.
    deadline = time.monotonic() + 5
    while git_op_in_flight(fetcher._source_id) and time.monotonic() < deadline:
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_a_timed_out_fetch_is_recorded_as_a_failure(tmp_path, monkeypatch):
    """Mutation: drop ``self._record_source_failure(exc)`` from the fetch
    TimeoutError handler (keep the clone one). A repo that WAS cloned once and
    whose host then went dark — the exact shape of the two prod SYN-drop hosts,
    which have clone dirs from before the outage — would then be re-attempted
    every pass, holding a slot for the whole SCOPES_GIT_FETCH_TIMEOUT each time.

    Drives a real hanging ``remote.fetch`` through run_in_git_executor, like the
    clone-side test, so the timeout wiring on the fetch path is what is asserted.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.2)
    fetcher = _fetcher(tmp_path, url="https://git/fetch-hangs.git")

    class _HangingRemote:
        def fetch(self, *args, **kwargs):
            time.sleep(0.5)  # well above the 0.2s timeout, short enough to reap

    class _RepoWithRemote:
        remotes = {"origin": _HangingRemote()}

    monkeypatch.setattr(fetcher, "_discover_repository", lambda path: True)
    monkeypatch.setattr(fetcher, "_get_valid_repo", lambda: _RepoWithRemote())

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    entry = GitPolicyFetcher.source_backoff[fetcher._source_id]
    assert entry.consecutive_failures == 1
    assert "TimeoutError" in entry.last_error

    deadline = time.monotonic() + 5
    while git_op_in_flight(fetcher._source_id) and time.monotonic() < deadline:
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_backpressure_is_not_a_source_failure(tmp_path, monkeypatch):
    """Mutation: record on a bare ``except Exception`` around the git call.
    GitConcurrencyLimitExceeded means the GLOBAL zombie cap refused this op —
    every scope is refused at that ceiling, healthy ones included — so
    recording it would put the whole fleet into backoff during one bad repo's
    outage, exactly inverting the intent."""
    from opal_server.git_fetcher import GitConcurrencyLimitExceeded

    fetcher = _fetcher(tmp_path)
    _fail_clone_with(monkeypatch, GitConcurrencyLimitExceeded("cap reached"))

    with pytest.raises(GitConcurrencyLimitExceeded):
        await fetcher.fetch_and_notify_on_changes()

    assert GitPolicyFetcher.source_backoff == {}


# --------------------------------------------------------------------------
# The kill switch
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("disabled", [0.0, -1.0, float("nan"), float("inf")])
async def test_the_key_disables_the_feature(tmp_path, monkeypatch, emitted, disabled):
    """Mutation: ``if cap <= 0`` -> ``if cap < 0`` (0 stops disabling), or drop
    the ``math.isfinite`` guard (inf means "back off forever", nan makes every
    comparison False). This key is the operator's only way out if the backoff
    ever suppresses a source it should not have."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_BACKOFF_MAX_SECONDS", disabled)
    fetcher = _fetcher(tmp_path)
    _fail_clone_with(monkeypatch, pygit2.GitError("remote unauthorized"))

    await fetcher.fetch_and_notify_on_changes()
    assert GitPolicyFetcher.source_backoff == {}, "recorded while disabled"

    # ...and a pre-existing entry (set before the key was flipped to 0) must
    # not suppress anything either.
    GitPolicyFetcher.source_backoff[fetcher._source_id] = SourceBackoff(
        consecutive_failures=5,
        next_attempt_at=time.monotonic() + 3600,
        last_error="boom",
    )
    await fetcher.fetch_and_notify_on_changes(honor_backoff=True)
    assert _counts(emitted, "opal_server.scopes.git_op_skipped") == []


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_gauge_is_tagged_by_pid_and_nothing_else(
    tmp_path, monkeypatch, emitted, no_jitter
):
    """Mutation: tag the gauge by source_id or scope_id. Every worker in the
    gunicorn pool emits this same series, so an untagged gauge reads as one
    arbitrary worker's count (the reason for the pid tag) — while a per-source
    tag makes the cardinality of a Datadog metric proportional to the customer
    count, which is the failure the existing _emit_git_ops_in_flight comment
    already calls out."""
    a = _fetcher(tmp_path, scope_id="a", url="https://git/a.git")
    b = _fetcher(tmp_path, scope_id="b", url="https://git/b.git")
    _fail_clone_with(monkeypatch, pygit2.GitError("remote unauthorized"))

    await a.fetch_and_notify_on_changes()
    await b.fetch_and_notify_on_changes()

    readings = _gauges(emitted, "opal_server.scopes.sources_in_backoff")
    assert [v for v, _ in readings] == [1, 2]
    assert all(tags == {"pid": str(os.getpid())} for _, tags in readings), readings


# --------------------------------------------------------------------------
# Process lifecycle: fork, reset, purge
# --------------------------------------------------------------------------


def test_reset_caches_keeps_the_backoff(tmp_path):
    """Mutation: add ``source_backoff.clear()`` to ``reset_caches``. The
    gunicorn master's pre-fork preload is where the boot-time clone failures
    are discovered; clearing them means every forked leader starts by
    re-hammering the same dead repos, which is precisely the boot storm this
    change is meant to collapse."""
    GitPolicyFetcher.source_backoff["src"] = SourceBackoff(1, time.monotonic(), "x")
    GitPolicyFetcher.repos_last_fetched["src"] = datetime.datetime.now()

    GitPolicyFetcher.reset_caches()

    assert "src" in GitPolicyFetcher.source_backoff
    assert (
        GitPolicyFetcher.repos_last_fetched == {}
    ), "the other caches must still clear"


def test_a_purged_source_forgets_its_backoff(tmp_path):
    """Mutation: drop ``forget_source_backoff`` from ``purge_local_memory``. A
    deleted or repointed source's entry would sit in the dict for the life of
    the process, counted in the gauge forever — and if the scope is re-created
    against the same URL, its first sync is suppressed by a dead scope's
    history."""
    GitPolicyFetcher.source_backoff["src"] = SourceBackoff(3, time.monotonic(), "x")

    purge_local_memory("src", str(tmp_path / "src"))

    assert GitPolicyFetcher.source_backoff == {}


@pytest.mark.asyncio
async def test_the_delete_floor_forgets_the_backoff(tmp_path, monkeypatch):
    """Mutation: drop ``forget_source_backoff`` from
    ``_purge_local_clone_best_effort``. Same leak as above on the path that
    does NOT go through the broadcaster — the floor that exists precisely
    because the purge broadcast is droppable."""
    scope = Scope(scope_id="gone", policy=_source("https://git/gone.git"), data={})
    source_id = GitPolicyFetcher.source_id(scope.policy)

    class _EmptyRepo:
        async def all(self):
            return []

    svc = ScopesService(base_dir=tmp_path, scopes=_EmptyRepo(), pubsub_endpoint=None)
    GitPolicyFetcher.source_backoff[source_id] = SourceBackoff(2, time.monotonic(), "x")

    await svc._purge_local_clone_best_effort(
        source_id,
        GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy),
        "gone",
    )

    assert GitPolicyFetcher.source_backoff == {}


# --------------------------------------------------------------------------
# End to end through sync_scopes
# --------------------------------------------------------------------------


class _FakeScopeRepository:
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


def _scope(scope_id, url):
    return Scope(scope_id=scope_id, policy=_source(url), data={"entries": []})


@pytest.mark.asyncio
async def test_one_pass_attempts_a_dead_source_once_not_once_per_scope(
    tmp_path, monkeypatch
):
    """Mutation: drop ``honor_backoff=honor_backoff`` from ``_sync_one``'s
    ``sync_scope`` call (or default ``sync_scopes``' parameter to False). This
    is the 2,410-attempts-per-3-hours case: one repo with many scopes, where
    phase 1 clones once and phase 2 re-attempts the clone for every duplicate
    because no local copy exists. Without the flag reaching the fetcher, the
    dead source is attempted once per scope, every pass, forever."""
    dead = [_scope(f"dead{i}", "https://git/dead.git") for i in range(5)]
    live = [_scope(f"live{i}", "https://git/live.git") for i in range(3)]
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=_FakeScopeRepository(dead + live),
        pubsub_endpoint=None,
    )
    dead_id = GitPolicyFetcher.source_id(dead[0].policy)
    live_id = GitPolicyFetcher.source_id(live[0].policy)

    attempts = []

    async def _fake(func, *args, timeout=None, busy_key=None, **kwargs):
        attempts.append(busy_key)
        if busy_key == dead_id:
            raise pygit2.GitError("remote unauthorized")
        return _FakeRepo()

    monkeypatch.setattr("opal_server.git_fetcher.run_in_git_executor", _fake)

    async def _no_notify(self, repo):
        return None

    monkeypatch.setattr(GitPolicyFetcher, "_notify_on_changes", _no_notify)

    await svc.sync_scopes(only_poll_updates=True, notify_on_changes=False)

    assert attempts.count(dead_id) == 1, (
        f"the dead source was attempted {attempts.count(dead_id)} times in one "
        f"pass; phase-2 duplicates are not honouring the backoff"
    )
    assert attempts.count(live_id) >= 1, "a healthy source must be unaffected"

    # A second pass, immediately after, must not touch the dead source at all.
    attempts.clear()
    await svc.sync_scopes(only_poll_updates=True, notify_on_changes=False)
    assert attempts.count(dead_id) == 0, attempts


@pytest.mark.asyncio
async def test_an_explicit_single_scope_sync_bypasses_the_pass_backoff(
    tmp_path, monkeypatch
):
    """Mutation: default ``ScopesService.sync_scope``'s ``honor_backoff`` to
    True. POST /scopes/{id}/refresh and PUT /scopes both land here; a customer
    who repairs their repo would get no sync until the backoff expired, with a
    200 OK telling them otherwise."""
    scope = _scope("s", "https://git/dead.git")
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=_FakeScopeRepository([scope]),
        pubsub_endpoint=None,
    )
    source_id = GitPolicyFetcher.source_id(scope.policy)
    GitPolicyFetcher.source_backoff[source_id] = SourceBackoff(
        consecutive_failures=6,
        next_attempt_at=time.monotonic() + 3600,
        last_error="boom",
    )

    attempts = []

    async def _fake(func, *args, timeout=None, busy_key=None, **kwargs):
        attempts.append(busy_key)
        return _FakeRepo()

    monkeypatch.setattr("opal_server.git_fetcher.run_in_git_executor", _fake)

    async def _no_notify(self, repo):
        return None

    monkeypatch.setattr(GitPolicyFetcher, "_notify_on_changes", _no_notify)

    await svc.sync_scope(scope_id="s", force_fetch=True, notify_on_changes=False)

    assert attempts == [source_id]
    assert source_id not in GitPolicyFetcher.source_backoff, "success must reset"


@pytest.mark.asyncio
async def test_refresh_all_does_not_honour_the_backoff(monkeypatch):
    """Mutation: have ``trigger(data=None)`` call ``_sync_all()`` with the
    default. POST /scopes/refresh is an operator explicitly asking every scope
    to sync now; answering it with a silent skip for the sources they most
    likely just repaired makes the endpoint useless in the one situation it is
    reached for. The boot call in ``start()`` keeps the default (honouring),
    which is what lets a forked leader inherit the master's boot failures."""
    from opal_server.scopes.task import ScopesPolicyWatcherTask

    seen = []

    class _Recorder:
        async def sync_scopes(self, *args, **kwargs):
            seen.append(kwargs.get("honor_backoff"))

    task = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    task._service = _Recorder()

    await task.trigger(topic=None, data=None)
    assert seen == [False]

    await task._sync_all()  # the boot path
    assert seen == [False, True]
