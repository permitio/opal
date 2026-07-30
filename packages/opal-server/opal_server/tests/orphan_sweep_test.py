"""Leader-only reconciliation sweep: clone dirs referencing no live scope are
reclaimed (bed gates: test_orphan_clone_dir_is_reclaimed,
test_redis_wiped_boot_reclaims_clones, red half of
test_shard_reconfig_still_serves_but_orphans_old_clones)."""
import asyncio
import shutil

import pytest
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    _mark_git_op_done,
    _mark_git_op_started,
)
from opal_server.scopes.purge import LeaderScopePurger, subscribe_worker_purge_handler
from opal_server.scopes.scope_repository import ScopeNotFoundError

# Valid source_id shape: 64 hex + "-<shard>" (matches purge._SOURCE_ID_RE). The
# sweep validates every dir name against this before rmtree (the SECURITY
# invariant every deletion path enforces), so these tests must use realistic
# names rather than short placeholders.
_SID = "deadbeef" * 8 + "-0"
_SID_BUSY = "b" * 64 + "-0"
_SID_RACE = "a" * 64 + "-0"
_SID_RAISE = "e" * 64 + "-0"


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        return list(self._scopes.values())


class FakePubSubEndpoint:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append((list(topics), data))


class CountingRepo(FakeScopeRepository):
    """FakeScopeRepository that counts store reads."""

    def __init__(self, scopes):
        super().__init__(scopes)
        self.all_calls = 0

    async def all(self):
        self.all_calls += 1
        return await super().all()


def _scope(scope_id, url, branch="main"):
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git",
            url=url,
            branch=branch,
            auth=NoAuthData(auth_type="none"),
        ),
        data={"entries": []},
    )


@pytest.fixture(autouse=True)
def clear_caches():
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()
    yield
    GitPolicyFetcher.repos.clear()
    GitPolicyFetcher.repos_last_fetched.clear()
    GitPolicyFetcher.repo_locks.clear()


def _git_sources(tmp_path):
    d = GitPolicyFetcher.base_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clone_dir_for(tmp_path, scope):
    clone = GitPolicyFetcher.repo_clone_path(tmp_path, scope.policy)
    clone.mkdir(parents=True)
    (clone / "marker").write_text("x")
    return clone


@pytest.mark.asyncio
async def test_orphan_dir_reclaimed_live_dir_kept(tmp_path):
    live = _scope("live", "https://git/live.git")
    live_clone = _clone_dir_for(tmp_path, live)
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()
    pubsub = FakePubSubEndpoint()

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([live]), pubsub_endpoint=pubsub
    )
    await purger.sweep_orphans()

    assert not orphan.exists()
    assert live_clone.exists()
    assert len(pubsub.published) == 1
    topics, payload = pubsub.published[0]
    assert topics == [opal_server_config.SCOPES_PURGE_CHANNEL]
    assert payload["source_id"] == _SID
    assert payload["reason"] == "orphan"
    assert payload["confirmed"] is True


@pytest.mark.asyncio
async def test_empty_store_with_clone_dirs_refuses_to_reclaim(tmp_path):
    """A SUCCESSFUL empty read is not proof that nothing is live.

    ScopeRepository.all() is a Redis SCAN loop: against an empty or
    wrong keyspace it returns zero keys and no error, so "the store is
    empty" and "we are reading the wrong store" are the same observation
    from in here (REDIS_URL on the wrong DB index, a failover to an
    empty replica, a stray FLUSHDB) — and reclaiming would delete every
    tenant's clone at once and broadcast confirmed purges fleet-wide.
    Refuse by default; only the guard-exception path was defended
    before.
    """
    from opal_common.logger import logger as opal_logger

    a = _clone_dir_for(tmp_path, _scope("a", "https://git/a.git"))
    b = _clone_dir_for(tmp_path, _scope("b", "https://git/b.git"))
    pubsub = FakePubSubEndpoint()

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="ERROR")
    try:
        await LeaderScopePurger(
            base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=pubsub
        ).sweep_orphans()
    finally:
        opal_logger.remove(sink)

    assert a.exists() and b.exists(), "an empty store wiped every live clone"
    assert pubsub.published == []
    assert any("refusing to reclaim" in r for r in records), f"not logged: {records}"


@pytest.mark.asyncio
async def test_empty_store_reclaims_everything_when_opted_in(tmp_path, monkeypatch):
    """The wiped-boot reclaim stays available, but only where an operator has
    asserted that an empty store really means no scopes exist (the git-leak
    bed's FLUSHALL gate sets this)."""
    monkeypatch.setattr(
        opal_server_config, "SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE", True
    )
    a = _clone_dir_for(tmp_path, _scope("a", "https://git/a.git"))
    b = _clone_dir_for(tmp_path, _scope("b", "https://git/b.git"))

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    await purger.sweep_orphans()

    assert not a.exists() and not b.exists()


@pytest.mark.asyncio
async def test_store_error_aborts_sweep_without_deleting(tmp_path):
    """A transient store error must abort the ENTIRE sweep before the per-entry
    loop — not be read as 'no scopes exist' (which would rmtree every live
    clone).

    The call-count assertion proves the abort happened at the initial
    scan, independent of the per-entry recheck's own guard.
    """

    class BrokenOnceRepo(FakeScopeRepository):
        def __init__(self, scopes):
            super().__init__(scopes)
            self.all_calls = 0

        async def all(self):
            self.all_calls += 1
            if self.all_calls == 1:
                raise RuntimeError("redis down")
            return await super().all()

    live_clone = _clone_dir_for(tmp_path, _scope("live", "https://git/live.git"))
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()
    pubsub = FakePubSubEndpoint()
    repo = BrokenOnceRepo([])  # empty: if the sweep wrongly continued with
    # live=set(), the recheck (a second .all() call) would succeed and
    # delete BOTH dirs — every assertion below discriminates.

    purger = LeaderScopePurger(base_dir=tmp_path, scopes=repo, pubsub_endpoint=pubsub)
    await purger.sweep_orphans()  # must not raise

    assert repo.all_calls == 1, "sweep continued past the failed initial scan"
    assert live_clone.exists() and orphan.exists()
    assert pubsub.published == []


@pytest.mark.asyncio
async def test_inflight_orphan_is_skipped(tmp_path):
    orphan = _git_sources(tmp_path) / _SID_BUSY
    orphan.mkdir()

    # One unrelated live scope so the store isn't empty — an empty store with
    # clone dirs present is refused outright (see
    # test_empty_store_with_clone_dirs_refuses_to_reclaim) and would mask this.
    purger = LeaderScopePurger(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([_scope("live", "https://git/live.git")]),
        pubsub_endpoint=None,
    )
    _mark_git_op_started(_SID_BUSY)
    try:
        await purger.sweep_orphans()
    finally:
        _mark_git_op_done(_SID_BUSY)

    assert orphan.exists(), "swept a dir a lingering git op still touches"
    # The dir/handle are deferred, but the repo_locks entry lock_source minted
    # for this candidate must NOT leak (invariant I4).
    assert (
        _SID_BUSY not in GitPolicyFetcher.repo_locks
    ), "in-flight defer left a stray lock"


@pytest.mark.asyncio
async def test_non_directory_junk_is_ignored(tmp_path):
    junk = _git_sources(tmp_path) / "stray-file"
    junk.write_text("not a clone")

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    )
    await purger.sweep_orphans()

    assert junk.exists()


@pytest.mark.asyncio
async def test_sweep_skips_live_dirs_without_a_recheck_scan(tmp_path):
    """The bulk case: dirs that map to a live scope in the snapshot are
    skipped with NO per-dir re-fetch — one scopes.all() total for an
    all-live tree."""
    live = [_scope(f"s{i}", f"https://git/r{i}.git") for i in range(4)]
    clones = [_clone_dir_for(tmp_path, s) for s in live]

    class CountingRepo(FakeScopeRepository):
        def __init__(self, scopes):
            super().__init__(scopes)
            self.all_calls = 0

        async def all(self):
            self.all_calls += 1
            return await super().all()

    repo = CountingRepo(live)
    await LeaderScopePurger(
        base_dir=tmp_path, scopes=repo, pubsub_endpoint=None
    ).sweep_orphans()

    assert repo.all_calls == 1, f"live dirs triggered {repo.all_calls} scans"
    for clone in clones:
        assert clone.exists()


@pytest.mark.asyncio
async def test_sweep_keeps_dir_reclaimed_by_a_put_between_snapshot_and_lock(
    tmp_path, monkeypatch
):
    """The race: a candidate orphan (absent from the initial snapshot) is
    re-claimed by a PUT before the sweep takes its lock. The fresh re-check
    must see the new scope and KEEP the clone."""
    orphan = _git_sources(tmp_path) / _SID_RACE
    orphan.mkdir()
    reclaimer = _scope("late", "https://git/late.git")
    filler = _scope("filler", "https://git/filler.git")
    # Make the reclaimer resolve to this exact dir name so it "owns" the
    # source once it lands (a real source_id hash won't match _SID_RACE). The
    # filler keeps the store non-empty (an empty store is refused outright) and
    # must NOT resolve to the candidate's name.
    monkeypatch.setattr(
        GitPolicyFetcher,
        "source_id",
        staticmethod(
            lambda p: _SID_RACE if p.url == "https://git/late.git" else "f" * 64 + "-9"
        ),
    )

    class ReclaimOnRecheck(FakeScopeRepository):
        def __init__(self, s):
            super().__init__(s)
            self.calls = 0

        async def all(self):
            self.calls += 1
            if self.calls >= 2:  # a PUT landed before the fresh re-check
                self._scopes["late"] = reclaimer
            return await super().all()

    repo = ReclaimOnRecheck([filler])  # candidate absent -> looks orphaned
    await LeaderScopePurger(
        base_dir=tmp_path, scopes=repo, pubsub_endpoint=None
    ).sweep_orphans()

    assert orphan.exists(), "a PUT that re-claimed the dir was clobbered by the sweep"
    assert repo.calls == 2, "candidate must trigger exactly one fresh re-check"


@pytest.mark.asyncio
async def test_sweep_logs_and_keeps_dir_when_recheck_raises(tmp_path):
    from opal_common.logger import logger as opal_logger

    orphan = _git_sources(tmp_path) / _SID_RAISE
    orphan.mkdir()
    live = _scope("live", "https://git/live.git")
    live_clone = _clone_dir_for(tmp_path, live)

    class RaiseOnRecheck(FakeScopeRepository):
        def __init__(self, s):
            super().__init__(s)
            self.calls = 0

        async def all(self):
            self.calls += 1
            if self.calls >= 2:
                raise RuntimeError("store scan failed on the fresh re-check")
            return await super().all()

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="WARNING")
    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=RaiseOnRecheck([live]), pubsub_endpoint=None
    )
    try:
        await purger.sweep_orphans()  # must not raise
    finally:
        opal_logger.remove(sink)

    assert orphan.exists(), "a raising re-check must keep the dir"
    assert live_clone.exists()
    assert any("keeping dir" in r for r in records), f"not logged: {records}"


@pytest.mark.asyncio
async def test_sweep_leaves_non_source_id_dirs_untouched(tmp_path):
    """Only names the clone path itself could have created may reach rmtree.

    The sweep's rmtree target comes from a directory listing, so the
    name is validated against the source-id shape first — the same
    SECURITY invariant _confined_clone_path enforces on pub/sub-supplied
    ids. An operator's `backup/` next to the clones must survive, and
    nothing may be published for it. Mutation: joining sources_dir /
    name raw (dropping the `is None` guard) must fail here.
    """
    live = _scope("live", "https://git/live.git")
    live_clone = _clone_dir_for(tmp_path, live)
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()
    junk = [
        _git_sources(tmp_path) / "backup",
        _git_sources(tmp_path) / "not-a-source-id",
        _git_sources(tmp_path) / ("z" * 64 + "-0"),  # right shape, wrong alphabet
        _git_sources(tmp_path) / ("a" * 63 + "-0"),  # one hex char short
    ]
    for d in junk:
        d.mkdir()
    pubsub = FakePubSubEndpoint()

    await LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([live]), pubsub_endpoint=pubsub
    ).sweep_orphans()

    assert not orphan.exists(), "the real orphan was not reclaimed"
    assert live_clone.exists()
    for d in junk:
        assert d.exists(), f"swept a dir the clone path never created: {d.name}"
    published_ids = [payload["source_id"] for _, payload in pubsub.published]
    assert published_ids == [_SID]


@pytest.mark.asyncio
async def test_all_live_pass_costs_one_scan(tmp_path):
    """The bulk case must stay cheap: dirs mapping to a live scope in the
    snapshot are skipped with NO per-dir store read, so an all-live tree costs
    exactly one scan however many dirs it has.

    This is the half of the round-3 perf fix that survives the round-4 HIGH: the
    authoritative read now happens only for dirs that actually look orphaned.
    """
    live = [_scope(f"s{i}", f"https://git/r{i}.git") for i in range(6)]
    clones = [_clone_dir_for(tmp_path, s) for s in live]

    repo = CountingRepo(live)
    await LeaderScopePurger(
        base_dir=tmp_path, scopes=repo, pubsub_endpoint=None
    ).sweep_orphans()

    assert repo.all_calls == 1, f"an all-live pass cost {repo.all_calls} scans"
    assert all(c.exists() for c in clones)


@pytest.mark.asyncio
async def test_each_candidate_gets_its_own_fresh_read(tmp_path):
    """Every candidate is re-checked against its own read, taken under its own
    lock: one snapshot plus one read per candidate."""
    # Enough live dirs that 3 candidates stay under the plausibility ceiling
    # (which is exercised on its own in the ceiling tests below).
    live = [_scope(f"live{i}", f"https://git/live{i}.git") for i in range(4)]
    live_clones = [_clone_dir_for(tmp_path, s) for s in live]
    orphans = []
    for i in range(3):
        d = _git_sources(tmp_path) / (f"{i}" * 64 + "-0")
        d.mkdir()
        orphans.append(d)

    repo = CountingRepo(live)
    await LeaderScopePurger(
        base_dir=tmp_path, scopes=repo, pubsub_endpoint=None
    ).sweep_orphans()

    assert repo.all_calls == 1 + len(orphans), (
        f"expected 1 snapshot + {len(orphans)} per-candidate reads, got "
        f"{repo.all_calls}"
    )
    assert all(not d.exists() for d in orphans)
    assert all(c.exists() for c in live_clones)


@pytest.mark.asyncio
async def test_candidate_that_goes_live_mid_pass_is_kept(tmp_path, monkeypatch):
    """A source that becomes live WHILE the pass deletes earlier candidates
    must not be reclaimed.

    The round-4 HIGH: the authoritative read has to happen inside each
    candidate's own lock_source. Any read hoisted out of the loop — batched, or
    re-taken every N candidates — is stale by the time later candidates are
    reached, so a PUT landing in that window is invisible and a LIVE tenant's
    clone dir is deleted, plus a confirmed orphan purge broadcast fleet-wide.
    That does not self-heal at the shipped defaults: POLICY_REFRESH_INTERVAL=0
    means nothing re-clones, so the scope serves 503 until a webhook or a manual
    refresh-all arrives.

    Mutation: hoist the read above the loop and reuse it -> victim deleted.
    """
    victim_sid = "a" * 64 + "-0"
    trigger_sid = "b" * 64 + "-0"
    victim = _git_sources(tmp_path) / victim_sid
    victim.mkdir()
    trigger = _git_sources(tmp_path) / trigger_sid
    trigger.mkdir()
    # Live fillers: keep the store non-empty (an empty store is refused outright)
    # and keep the candidate share under the plausibility ceiling.
    fillers = [_scope(f"filler{i}", f"https://git/filler{i}.git") for i in range(6)]
    for f in fillers:
        _clone_dir_for(tmp_path, f)
    reclaimer = _scope("late", "https://git/late.git")
    monkeypatch.setattr(
        GitPolicyFetcher,
        "source_id",
        staticmethod(
            lambda pol: victim_sid
            if pol.url == "https://git/late.git"
            else "f" * 64 + f"-{abs(hash(pol.url)) % 90 + 9}"
        ),
    )

    events = []
    repo = FakeScopeRepository(fillers)
    real_rmtree = shutil.rmtree

    def _rmtree_spy(path, *a, **kw):
        # The PUT lands while an EARLIER candidate is being deleted — precisely
        # the window a hoisted read cannot observe.
        if str(path).endswith(trigger_sid):
            repo._scopes["late"] = reclaimer
            events.append("PUT: victim became live")
        events.append(
            "rmtree " + ("trigger" if str(path).endswith(trigger_sid) else "victim")
        )
        return real_rmtree(path, *a, **kw)

    monkeypatch.setattr(shutil, "rmtree", _rmtree_spy)
    pubsub = FakePubSubEndpoint()

    await LeaderScopePurger(
        base_dir=tmp_path, scopes=repo, pubsub_endpoint=pubsub
    ).sweep_orphans()

    purged = [payload["source_id"] for _, payload in pubsub.published]
    assert victim.exists(), (
        f"reclaimed a clone whose source went live mid-pass — a stale live-set "
        f"was used for the delete decision (events: {events})"
    )
    assert (
        victim_sid not in purged
    ), "broadcast a confirmed orphan purge for a live source"


@pytest.mark.asyncio
async def test_wrong_but_populated_keyspace_is_refused_by_the_ceiling(tmp_path):
    """The zero-scope guard cannot see a store pointed at the WRONG keyspace: it
    answers successfully with someone else's scopes, none of whose source_ids
    match the local dirs, so every clone looks orphaned.

    The ceiling catches it without having to tell a wrong store from a right one
    — it only notices that one pass is about to delete an implausible share.
    Mutation: drop the ceiling call -> all five production clones deleted.
    """
    from opal_common.logger import logger as opal_logger

    ours = [_scope(f"prod{i}", f"https://git/prod{i}.git") for i in range(5)]
    clones = [_clone_dir_for(tmp_path, s) for s in ours]
    # The store answers with two unrelated scopes from another environment.
    theirs = [
        _scope("other-a", "https://git/other-a.git"),
        _scope("other-b", "https://git/other-b.git"),
    ]
    pubsub = FakePubSubEndpoint()

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="ERROR")
    try:
        await LeaderScopePurger(
            base_dir=tmp_path,
            scopes=FakeScopeRepository(theirs),
            pubsub_endpoint=pubsub,
        ).sweep_orphans()
    finally:
        opal_logger.remove(sink)

    assert all(c.exists() for c in clones), "a wrong keyspace wiped the clone tree"
    assert pubsub.published == []
    assert any("look orphaned in a single pass" in r for r in records), records


@pytest.mark.asyncio
async def test_single_candidate_is_always_allowed(tmp_path):
    """The ordinary case — one stale dir beside one live scope — must never be
    blocked by the ceiling, or a small tree would never be swept at all."""
    live = _scope("live", "https://git/live.git")
    live_clone = _clone_dir_for(tmp_path, live)
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()

    await LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([live]), pubsub_endpoint=None
    ).sweep_orphans()

    assert not orphan.exists(), "the ordinary single-orphan reclaim was blocked"
    assert live_clone.exists()


@pytest.mark.asyncio
async def test_ceiling_can_be_disabled_for_a_deliberate_reshard(tmp_path, monkeypatch):
    """A SCOPES_REPO_CLONES_SHARDS reconfig legitimately orphans most of the
    tree; the operator has a dial for it."""
    monkeypatch.setattr(
        opal_server_config, "SCOPES_ORPHAN_SWEEP_MAX_RECLAIM_FRACTION", 0.0
    )
    live = _scope("live", "https://git/live.git")
    _clone_dir_for(tmp_path, live)
    orphans = []
    for i in range(4):
        d = _git_sources(tmp_path) / (f"{i}" * 64 + "-0")
        d.mkdir()
        orphans.append(d)

    await LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([live]), pubsub_endpoint=None
    ).sweep_orphans()

    assert all(not d.exists() for d in orphans), "ceiling still applied when disabled"


@pytest.mark.asyncio
async def test_opted_in_empty_store_reclaim_is_not_vetoed_by_the_ceiling(
    tmp_path, monkeypatch
):
    """The empty-store opt-in is itself a declaration of intent for a mass
    reclaim, so the ceiling must not turn it into a no-op on any tree bigger
    than one dir."""
    monkeypatch.setattr(
        opal_server_config, "SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE", True
    )
    dirs = [
        _clone_dir_for(tmp_path, _scope(f"s{i}", f"https://git/r{i}.git"))
        for i in range(4)
    ]

    await LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    ).sweep_orphans()

    assert all(not d.exists() for d in dirs)


@pytest.mark.asyncio
async def test_heartbeat_reports_outcome_and_partial_count_on_abort(
    tmp_path, monkeypatch
):
    """Every exit path logs the heartbeat with an explicit outcome, including
    aborts — an aborted pass must not be indistinguishable from a healthy
    "swept, found nothing" one, and must not discard what it already
    reclaimed."""
    from opal_common.logger import logger as opal_logger

    live = [_scope(f"live{i}", f"https://git/live{i}.git") for i in range(4)]
    for s in live:
        _clone_dir_for(tmp_path, s)
    first = _git_sources(tmp_path) / ("1" * 64 + "-0")
    first.mkdir()
    second = _git_sources(tmp_path) / ("2" * 64 + "-0")
    second.mkdir()

    class EmptiesAfterOneDelete(FakeScopeRepository):
        def __init__(self, scopes):
            super().__init__(scopes)
            self.reads = 0

        async def all(self):
            self.reads += 1
            # snapshot + first candidate's check are normal; then the store goes
            # empty mid-pass (a FLUSHDB / failover / wrong reload).
            if self.reads > 2:
                return []
            return list(self._scopes.values())

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="INFO")
    try:
        await LeaderScopePurger(
            base_dir=tmp_path,
            scopes=EmptiesAfterOneDelete(live),
            pubsub_endpoint=None,
        ).sweep_orphans()
    finally:
        opal_logger.remove(sink)

    beat = [r for r in records if "Orphan sweep" in r and "scanned" in r]
    assert len(beat) == 1, f"expected exactly one heartbeat, got: {beat}"
    assert "aborted" in beat[0], f"abort not reported in the heartbeat: {beat[0]}"
    assert (
        "reclaimed 1" in beat[0]
    ), f"heartbeat discarded the dir already reclaimed before the abort: {beat[0]}"


@pytest.mark.asyncio
async def test_failed_rmtree_leaves_no_stray_repo_lock(tmp_path, monkeypatch):
    """A dir that can never be reclaimed (EPERM, read-only mount, a symlink)
    must not leak the repo_locks entry lock_source minted for it — one stray
    per distinct failing source id, forever, in a PR whose purpose is not
    leaking these dicts (invariant I4).

    Mutation: `continue` past the pop -> stray lock.
    """
    live = _scope("live", "https://git/live.git")
    _clone_dir_for(tmp_path, live)
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()

    def _boom(path, *a, **kw):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(shutil, "rmtree", _boom)

    await LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([live]), pubsub_endpoint=None
    ).sweep_orphans()

    assert orphan.exists()  # unreclaimable, as expected
    assert (
        _SID not in GitPolicyFetcher.repo_locks
    ), "a failed reclaim left a stray repo_locks entry"


@pytest.mark.asyncio
async def test_sweep_inline_confirmation_does_not_deadlock(tmp_path, monkeypatch):
    """The sweep's confirmation publish re-enters lock_source, exactly like the
    leader delete path's.

    ``publish()`` runs local subscribers inline on this task, and
    ``handle_purge_message`` takes ``lock_source(source_id)`` — the same
    non-reentrant lock the sweep is holding. The only reason it is not a deadlock
    is that ``repo_locks.pop`` runs BEFORE the publish, so the handler mints a
    fresh lock. Every other sweep test uses ``FakePubSubEndpoint``, which appends
    to a list and never delivers inline, so none of them can observe this.

    Mutation: move the pop below the publish ("clean up last") -> this hangs,
    hence the wait_for, and fails fast instead of wedging CI.
    """
    monkeypatch.setattr(
        "opal_server.scopes.purge.opal_server_config.BASE_DIR", str(tmp_path)
    )
    live = _scope("live", "https://git/live.git")
    _clone_dir_for(tmp_path, live)
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()
    GitPolicyFetcher.repos[str(orphan)] = object()

    endpoint = PubSubEndpoint()  # real EventNotifier, inline local delivery
    await subscribe_worker_purge_handler(endpoint)  # the every-worker handler
    received = []

    async def _recorder(subscription, data):
        received.append(data)

    await endpoint.subscribe([opal_server_config.SCOPES_PURGE_CHANNEL], _recorder)

    await asyncio.wait_for(
        LeaderScopePurger(
            base_dir=tmp_path,
            scopes=FakeScopeRepository([live]),
            pubsub_endpoint=endpoint,
        ).sweep_orphans(),
        timeout=3,
    )

    assert not orphan.exists()
    # Proves the confirmation really was delivered inline, so the no-deadlock
    # assertion above is meaningful rather than vacuous.
    assert [d["reason"] for d in received] == ["orphan"]
    assert _SID not in GitPolicyFetcher.repo_locks


@pytest.mark.asyncio
async def test_sweep_waits_for_the_source_lock_before_deleting(tmp_path):
    """The per-candidate ``lock_source`` is the sweep's only serialisation
    against a concurrent clone/fetch for that source — every
    ``run_in_git_executor`` call site sits inside
    ``fetch_and_notify_on_changes`` or ``_clone``, both under the same lock —
    and both the sweep's docstring and its under-lock re-check lean on it being
    held.

    Mutation: neutralise the ``async with lock_source(name)`` -> the dir is
    deleted while a holder owns the lock and this fails.
    """
    live = _scope("live", "https://git/live.git")
    live_clone = _clone_dir_for(tmp_path, live)
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()

    holder = GitPolicyFetcher.repo_locks.setdefault(_SID, asyncio.Lock())
    await holder.acquire()  # stands in for a sync holding the source
    task = asyncio.create_task(
        LeaderScopePurger(
            base_dir=tmp_path,
            scopes=FakeScopeRepository([live]),
            pubsub_endpoint=None,
        ).sweep_orphans()
    )
    try:
        for _ in range(10):
            await asyncio.sleep(0)
        assert orphan.exists(), "swept a dir while another holder owned lock_source"
        assert not task.done()
    finally:
        holder.release()

    await asyncio.wait_for(task, timeout=2)
    assert not orphan.exists()  # reclaimed once the lock was free
    assert live_clone.exists()


@pytest.mark.asyncio
async def test_missing_base_dir_still_heartbeats(tmp_path):
    """A monitor must never see the same thing for "the sweeper ran and had
    nothing to do" and "the sweeper died" — including on the no-clone-dir
    path."""
    from opal_common.logger import logger as opal_logger

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="INFO")
    try:
        await LeaderScopePurger(
            base_dir=tmp_path / "never-created",
            scopes=FakeScopeRepository([]),
            pubsub_endpoint=None,
        ).sweep_orphans()
    finally:
        opal_logger.remove(sink)

    beat = [r for r in records if "Orphan sweep" in r and "scanned" in r]
    assert len(beat) == 1, f"no heartbeat on the no-clone-dir path: {records}"
    assert "skipped (no clone dir)" in beat[0], beat[0]
