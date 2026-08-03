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
from opal_server.scopes.purge import (
    _REQUIRED_ORPHAN_STREAK,
    LeaderScopePurger,
    subscribe_worker_purge_handler,
)
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


async def _sweep_until_reclaimed(purger, passes=_REQUIRED_ORPHAN_STREAK):
    """Run the sweep enough times for corroboration to be satisfied.

    A dir must look orphaned for `_REQUIRED_ORPHAN_STREAK` consecutive passes
    before it is eligible, so any test asserting a RECLAIM must sweep that many
    times. Tests asserting that nothing is deleted deliberately sweep once —
    passing there would be ambiguous (kept on purpose, or merely not yet
    corroborated), so they say which they mean.
    """
    for _ in range(passes):
        await purger.sweep_orphans()


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
    await _sweep_until_reclaimed(purger)

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
    await _sweep_until_reclaimed(purger)

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
    await _sweep_until_reclaimed(
        LeaderScopePurger(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)
    )

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
            # 1: pass-1 snapshot, 2: pass-2 snapshot, 3+: the under-lock
            # re-check for a now-corroborated candidate — the path under test.
            if self.calls >= 3:
                raise RuntimeError("store scan failed on the fresh re-check")
            return await super().all()

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="WARNING")
    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=RaiseOnRecheck([live]), pubsub_endpoint=None
    )
    try:
        await _sweep_until_reclaimed(purger)  # must not raise
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

    await _sweep_until_reclaimed(
        LeaderScopePurger(
            base_dir=tmp_path,
            scopes=FakeScopeRepository([live]),
            pubsub_endpoint=pubsub,
        )
    )

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
    """Each dir that is actually about to be deleted is re-checked against its
    OWN read, taken under its own lock — and only those pay for a read.

    This is the shape that ends the freshness-vs-cost oscillation: freshness is
    per candidate (a batched read goes stale as the loop deletes), but the number
    of candidates that reach a read is bounded by the per-pass cap, so the pass
    is O(cap) store reads rather than O(orphans x scopes).
    """
    monkeypatch = None  # (kept explicit: this test relies on the shipped cap)
    cap = opal_server_config.SCOPES_ORPHAN_SWEEP_MAX_RECLAIM_PER_PASS
    live = [_scope(f"live{i}", f"https://git/live{i}.git") for i in range(4)]
    live_clones = [_clone_dir_for(tmp_path, s) for s in live]
    orphans = []
    for i in range(cap + 2):  # more orphans than one pass may reclaim
        d = _git_sources(tmp_path) / (f"{i:x}" * 64 + "-0")
        d.mkdir()
        orphans.append(d)

    repo = CountingRepo(live)
    purger = LeaderScopePurger(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    await purger.sweep_orphans()  # pass 1: corroboration only, nothing eligible
    assert repo.all_calls == 1, "an un-corroborated pass must not read per candidate"
    assert all(d.exists() for d in orphans), "reclaimed before corroboration"

    await purger.sweep_orphans()  # pass 2: up to `cap` reclaims, one read each
    assert repo.all_calls == 2 + cap, (
        f"expected 1 snapshot + {cap} per-candidate reads on the second pass, "
        f"got {repo.all_calls - 1}"
    )
    assert sum(not d.exists() for d in orphans) == cap, "the cap was not honoured"
    assert all(c.exists() for c in live_clones)


@pytest.mark.asyncio
async def test_candidate_that_goes_live_mid_pass_is_kept(tmp_path, monkeypatch):
    """A source that becomes live WHILE the pass deletes an earlier candidate
    must not be reclaimed.

    The authoritative read has to happen inside each candidate's own
    lock_source. Any read hoisted out of the loop — batched, or re-taken every N
    candidates — is stale by the time later candidates are reached, so a PUT
    landing in that window is invisible and a LIVE tenant's clone dir is deleted,
    plus a confirmed orphan purge broadcast fleet-wide. That does not self-heal
    at the shipped defaults: POLICY_REFRESH_INTERVAL=0 means nothing re-clones,
    so the scope serves 503 until a webhook or a manual refresh-all.

    Mutation: cache the first `self._scopes.all()` in _classify_candidate and
    reuse it (the pre-round-4 batched read) -> the victim is deleted.

    NOTE the ordering below: `source_id` is patched BEFORE the filler clone dirs
    are created, so their on-disk names match the patched live set. An earlier
    version of this test patched it afterwards, every dir became a candidate, the
    pass refused before the loop was entered, and the victim survived for a
    reason that had nothing to do with freshness — it could not fail.
    """
    sid_a = "a" * 64 + "-0"
    sid_b = "b" * 64 + "-0"
    # Which dir goes live is decided at runtime, from whichever one the pass
    # deletes FIRST — os.scandir order is not guaranteed, and pinning the
    # scenario to a fixed order would make this test pass or fail by luck.
    late_target = {"sid": None}
    filler_sids = {
        f"https://git/filler{i}.git": f"{i + 3}" * 64 + "-0" for i in range(4)
    }
    monkeypatch.setattr(
        GitPolicyFetcher,
        "source_id",
        staticmethod(
            lambda pol: late_target["sid"]
            if pol.url == "https://git/late.git"
            else filler_sids[pol.url]
        ),
    )
    # Fillers first, now that source_id is patched: their dir names come from the
    # patched function, so they land in live_source_ids and are NOT candidates.
    fillers = [_scope(f"filler{i}", f"https://git/filler{i}.git") for i in range(4)]
    filler_clones = [_clone_dir_for(tmp_path, f) for f in fillers]
    dirs = {}
    for sid in (sid_a, sid_b):
        d = _git_sources(tmp_path) / sid
        d.mkdir()
        dirs[sid] = d

    events = []
    repo = FakeScopeRepository(fillers)
    real_rmtree = shutil.rmtree

    def _rmtree_spy(path, *a, **kw):
        name = str(path).rstrip("/").rsplit("/", 1)[-1]
        if not events:
            # A PUT re-claims the OTHER candidate while this one is being
            # deleted — precisely the window a hoisted read cannot observe.
            late_target["sid"] = sid_b if name == sid_a else sid_a
            repo._scopes["late"] = _scope("late", "https://git/late.git")
            events.append(f"PUT: {late_target['sid'][:4]}… became live")
        events.append(f"rmtree {name[:4]}…")
        return real_rmtree(path, *a, **kw)

    monkeypatch.setattr(shutil, "rmtree", _rmtree_spy)
    pubsub = FakePubSubEndpoint()
    purger = LeaderScopePurger(base_dir=tmp_path, scopes=repo, pubsub_endpoint=pubsub)
    await _sweep_until_reclaimed(purger)

    assert events, "the pass never reached the deletion loop, so this proves nothing"
    victim_sid = late_target["sid"]
    purged = [payload["source_id"] for _, payload in pubsub.published]
    assert dirs[victim_sid].exists(), (
        f"reclaimed a clone whose source went live mid-pass — a stale live-set "
        f"was used for the delete decision (events: {events})"
    )
    assert (
        victim_sid not in purged
    ), "broadcast a confirmed orphan purge for a live source"
    assert all(c.exists() for c in filler_clones)


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
            # 1: pass-1 snapshot. 2: pass-2 snapshot. 3: the first corroborated
            # candidate's under-lock re-check. Then the store goes empty
            # mid-pass (a FLUSHDB / failover / wrong reload).
            if self.reads > 3:
                return []
            return list(self._scopes.values())

    purger = LeaderScopePurger(
        base_dir=tmp_path,
        scopes=EmptiesAfterOneDelete(live),
        pubsub_endpoint=None,
    )
    await purger.sweep_orphans()  # corroborate; nothing eligible yet

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="INFO")
    try:
        await purger.sweep_orphans()
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

    from opal_common.logger import logger as opal_logger

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="WARNING")
    try:
        await _sweep_until_reclaimed(
            LeaderScopePurger(
                base_dir=tmp_path,
                scopes=FakeScopeRepository([live]),
                pubsub_endpoint=None,
            )
        )
    finally:
        opal_logger.remove(sink)

    # Not vacuous: prove the reclaim was actually ATTEMPTED. Without this the
    # test would pass if some future guard stopped the candidate from ever
    # reaching the deletion (both assertions below hold when nothing happened).
    assert any(
        "Failed to reclaim orphan" in r for r in records
    ), f"the reclaim was never attempted, so this test proves nothing: {records}"
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

    purger = LeaderScopePurger(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([live]),
        pubsub_endpoint=endpoint,
    )
    # wait_for wraps the pass that actually reclaims (and therefore publishes),
    # since that is the one that can deadlock.
    await purger.sweep_orphans()  # corroborate
    await asyncio.wait_for(purger.sweep_orphans(), timeout=3)

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

    purger = LeaderScopePurger(
        base_dir=tmp_path,
        scopes=FakeScopeRepository([live]),
        pubsub_endpoint=None,
    )
    # First pass only corroborates (nothing is eligible yet); the lock matters on
    # the pass that would actually delete.
    await purger.sweep_orphans()

    holder = GitPolicyFetcher.repo_locks.setdefault(_SID, asyncio.Lock())
    await holder.acquire()  # stands in for a sync holding the source
    task = asyncio.create_task(purger.sweep_orphans())
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


@pytest.mark.asyncio
async def test_no_stray_lock_when_a_candidate_is_kept_or_the_pass_aborts(
    tmp_path, monkeypatch
):
    """A candidate is by definition a source no live scope claims, so the
    repo_locks entry lock_source mints for it must not outlive the pass on ANY
    path — including the two that decline to delete.

    The keep-on-error and mid-pass-abort paths are reached precisely
    when the store could not confirm the source is live, so leaving the
    entry behind is a stray lock with no live scope (invariant I4, which
    the git-leak bed checks at every teardown). Mutation: move the pop
    back inside the deletion attempt -> one stray per aborted or kept
    candidate.
    """
    live = [_scope(f"l{i}", f"https://git/l{i}.git") for i in range(4)]
    for s in live:
        _clone_dir_for(tmp_path, s)
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()
    live_ids = {GitPolicyFetcher.source_id(s.policy) for s in live}

    class EmptiesMidPass(FakeScopeRepository):
        def __init__(self, scopes):
            super().__init__(scopes)
            self.reads = 0

        async def all(self):
            self.reads += 1
            return [] if self.reads > 1 else list(self._scopes.values())

    class RaisesMidPass(FakeScopeRepository):
        def __init__(self, scopes):
            super().__init__(scopes)
            self.reads = 0

        async def all(self):
            self.reads += 1
            if self.reads > 1:
                raise RuntimeError("store blip on the under-lock re-check")
            return list(self._scopes.values())

    for store in (EmptiesMidPass(live), RaisesMidPass(live)):
        GitPolicyFetcher.repo_locks.clear()
        await LeaderScopePurger(
            base_dir=tmp_path, scopes=store, pubsub_endpoint=None
        ).sweep_orphans()
        stray = set(GitPolicyFetcher.repo_locks) - live_ids
        assert not stray, (
            f"{type(store).__name__} left a stray repo_locks entry with no live "
            f"scope (I4): {sorted(stray)}"
        )
        assert orphan.exists(), "neither path should have deleted the dir"


@pytest.mark.asyncio
async def test_hung_store_read_does_not_pin_the_source_lock(tmp_path, monkeypatch):
    """The under-lock store read must be bounded.

    RedisDB is built with no socket_timeout/socket_connect_timeout, so redis-py
    waits forever; since this read is held under the candidate's lock_source (it
    has to be, to be authoritative), an unreachable store would otherwise pin
    that source's lock for the life of the process and block all of its syncs.
    Expiry is safe: the candidate is KEPT. Mutation: drop the wait_for and this
    hangs.
    """
    monkeypatch.setattr(
        opal_server_config, "SCOPES_ORPHAN_SWEEP_STORE_READ_TIMEOUT", 0.05
    )
    live = _scope("live", "https://git/live.git")
    live_clone = _clone_dir_for(tmp_path, live)
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()

    class HangsOnRecheck(FakeScopeRepository):
        def __init__(self, scopes):
            super().__init__(scopes)
            self.reads = 0

        async def all(self):
            self.reads += 1
            # Both passes' snapshots succeed; the under-lock re-check hangs.
            if self.reads > 2:
                await asyncio.sleep(3600)
            return list(self._scopes.values())

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=HangsOnRecheck([live]), pubsub_endpoint=None
    )
    await asyncio.wait_for(_sweep_until_reclaimed(purger), timeout=10)

    assert orphan.exists(), "a timed-out re-check must keep the dir"
    assert live_clone.exists()
    assert not GitPolicyFetcher.repo_locks, "the hung read left the source lock held"


@pytest.mark.asyncio
async def test_transient_store_loss_never_deletes_a_live_clone(tmp_path):
    """A store that is briefly INCOMPLETE must not cost a tenant its clone.

    This is the case no single read can catch, however fresh: a replica seconds
    behind after a failover, an LRU eviction of `permit.io/Scope:*` (they are SET
    with no TTL, so they are evictable), a partial restore. The under-lock
    re-check reads the same degraded store, so it confirms the wrong answer
    rather than catching it — corroboration across passes is what covers it,
    because the record is back before the second pass.

    Mutation: drop the streak requirement -> the clone is deleted.
    """
    live = [_scope(f"t{i}", f"https://git/t{i}.git") for i in range(6)]
    clones = {s.scope_id: _clone_dir_for(tmp_path, s) for s in live}
    pubsub = FakePubSubEndpoint()

    class LosesTwoRecordsForOnePass(FakeScopeRepository):
        def __init__(self, scopes):
            super().__init__(scopes)
            self.passes = 0

        async def all(self):
            self.passes += 1
            records = list(self._scopes.values())
            # Only the first pass is degraded; afterwards the store is correct.
            return records[2:] if self.passes == 1 else records

    purger = LeaderScopePurger(
        base_dir=tmp_path,
        scopes=LosesTwoRecordsForOnePass(live),
        pubsub_endpoint=pubsub,
    )
    await _sweep_until_reclaimed(purger)
    await purger.sweep_orphans()  # a third pass, to be sure nothing lingers

    assert all(c.exists() for c in clones.values()), (
        "a transient store gap deleted live tenants' clones: "
        f"{[k for k, c in clones.items() if not c.exists()]}"
    )
    assert pubsub.published == [], "broadcast an orphan purge for a live source"


@pytest.mark.asyncio
async def test_reclaim_is_capped_per_pass_and_drains_over_passes(tmp_path, monkeypatch):
    """The cap bounds how much one pass can delete — the blast radius of a
    store that is persistently wrong — without leaking: the backlog drains over
    consecutive passes."""
    monkeypatch.setattr(
        opal_server_config, "SCOPES_ORPHAN_SWEEP_MAX_RECLAIM_PER_PASS", 2
    )
    live = _scope("live", "https://git/live.git")
    live_clone = _clone_dir_for(tmp_path, live)
    orphans = []
    for i in range(5):
        d = _git_sources(tmp_path) / (f"{i}" * 64 + "-0")
        d.mkdir()
        orphans.append(d)

    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([live]), pubsub_endpoint=None
    )
    await purger.sweep_orphans()
    assert sum(not d.exists() for d in orphans) == 0, "reclaimed before corroboration"

    for expected in (2, 4, 5, 5):
        await purger.sweep_orphans()
        assert sum(not d.exists() for d in orphans) == expected, (
            f"expected {expected} reclaimed by now, got "
            f"{sum(not d.exists() for d in orphans)}"
        )
    assert live_clone.exists()


@pytest.mark.asyncio
async def test_unrecognised_dirs_do_not_change_the_guards_arithmetic(tmp_path):
    """A name the clone path never created must appear in NO guard's counting.

    Such names can never be candidates (they fail `_confined_clone_path`), so
    counting them as part of the tree would let junk buy headroom for a
    mass-reclaim — an operator's `clone.bak`, a `lost+found` on a PVC, or a
    symlink (scandir follows them) is enough. The same raw count also made a
    legitimately empty store report "N clone dirs exist" and refuse forever.
    """
    from opal_common.logger import logger as opal_logger

    for junk in ("backup", "lost+found", "not-a-source-id", "clone.bak"):
        (_git_sources(tmp_path) / junk).mkdir()

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="ERROR")
    try:
        await LeaderScopePurger(
            base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
        ).sweep_orphans()
    finally:
        opal_logger.remove(sink)

    assert not [
        r for r in records if "refusing to reclaim" in r
    ], f"junk dirs were counted as clone dirs by the empty-store guard: {records}"
    for junk in ("backup", "lost+found", "not-a-source-id", "clone.bak"):
        assert (_git_sources(tmp_path) / junk).exists()


@pytest.mark.asyncio
async def test_disabling_the_reclaim_cap_is_announced_once(tmp_path, monkeypatch):
    """Turning a destructive-path safety control off deserves an audit line —
    and exactly one, not one per pass forever.

    The previous fraction knob had this backwards: typos warned, while the values
    an operator would actually type to disable it were silent.
    """
    from opal_common.logger import logger as opal_logger

    monkeypatch.setattr(
        "opal_server.scopes.purge._reclaim_cap_disabled_warned", False, raising=False
    )
    monkeypatch.setattr(
        opal_server_config, "SCOPES_ORPHAN_SWEEP_MAX_RECLAIM_PER_PASS", 0
    )
    live = _scope("live", "https://git/live.git")
    _clone_dir_for(tmp_path, live)
    orphans = []
    for i in range(4):
        d = _git_sources(tmp_path) / (f"{i}" * 64 + "-0")
        d.mkdir()
        orphans.append(d)

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="WARNING")
    try:
        purger = LeaderScopePurger(
            base_dir=tmp_path, scopes=FakeScopeRepository([live]), pubsub_endpoint=None
        )
        await _sweep_until_reclaimed(purger)
        await purger.sweep_orphans()
    finally:
        opal_logger.remove(sink)

    warned = [r for r in records if "disables the" in r and "reclaim cap" in r]
    assert len(warned) == 1, f"expected exactly one audit line, got {len(warned)}"
    assert all(not d.exists() for d in orphans), "the cap should be off"


@pytest.mark.asyncio
async def test_undecidable_candidates_make_the_pass_degraded_not_complete(
    tmp_path, monkeypatch
):
    """A pass that could not DECIDE must not report `complete`.

    The heartbeat is what a monitor watches. A timed-out store read
    keeps the candidate — correct — but reporting that as "swept, found
    nothing" hides a backstop that is effectively off. Mutation: return
    "claimed" instead of "undecided" -> the heartbeat says complete and
    this fails.
    """
    from opal_common.logger import logger as opal_logger

    monkeypatch.setattr(
        opal_server_config, "SCOPES_ORPHAN_SWEEP_STORE_READ_TIMEOUT", 0.05
    )
    events = []
    monkeypatch.setattr(
        "opal_server.scopes.purge.metrics.event",
        lambda title, message=None, tags=None: events.append(
            (title, (tags or {}).get("reason"))
        ),
    )
    live = _scope("live", "https://git/live.git")
    _clone_dir_for(tmp_path, live)
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()

    class HangsOnRecheck(FakeScopeRepository):
        def __init__(self, scopes):
            super().__init__(scopes)
            self.reads = 0

        async def all(self):
            self.reads += 1
            if self.reads > 2:  # both snapshots fine; the re-check hangs
                await asyncio.sleep(3600)
            return list(self._scopes.values())

    records = []
    sink = opal_logger.add(lambda m: records.append(str(m)), level="INFO")
    try:
        purger = LeaderScopePurger(
            base_dir=tmp_path, scopes=HangsOnRecheck([live]), pubsub_endpoint=None
        )
        await asyncio.wait_for(_sweep_until_reclaimed(purger), timeout=10)
    finally:
        opal_logger.remove(sink)

    beat = [r for r in records if "Orphan sweep" in r and "scanned" in r][-1]
    assert "degraded" in beat, f"an undecidable pass reported: {beat}"
    assert orphan.exists(), "deleted on a read that never answered"
    assert (
        "ScopeOrphanSweepRefused",
        "store_read_timeout",
    ) in events, f"no metric for the timeout: {events}"


@pytest.mark.asyncio
async def test_refusal_metric_fires_with_a_reason_tag(tmp_path, monkeypatch):
    """The metric added so the refusal is visible to a monitor (not only to a
    log-scraper) had no test on any path.

    Deleting the calls left the suite green.
    """
    events = []
    monkeypatch.setattr(
        "opal_server.scopes.purge.metrics.event",
        lambda title, message=None, tags=None: events.append(
            (title, (tags or {}).get("reason"))
        ),
    )
    _clone_dir_for(tmp_path, _scope("a", "https://git/a.git"))

    # empty store with clone dirs present
    await LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([]), pubsub_endpoint=None
    ).sweep_orphans()
    assert ("ScopeOrphanSweepRefused", "empty_store") in events, events

    # store scan raises
    class Broken(FakeScopeRepository):
        async def all(self):
            raise RuntimeError("redis down")

    events.clear()
    await LeaderScopePurger(
        base_dir=tmp_path, scopes=Broken([]), pubsub_endpoint=None
    ).sweep_orphans()
    assert ("ScopeOrphanSweepRefused", "scan_failed") in events, events


@pytest.mark.asyncio
async def test_cancelled_sweep_still_publishes_its_confirmation(tmp_path, monkeypatch):
    """A SIGTERM landing mid-reclaim must not delete the dir and skip the
    broadcast.

    `run_sync` dispatches rmtree to the loop's default executor, so cancelling
    the sweep does not cancel the thread — the directory goes regardless. If the
    confirmation is skipped, every OTHER worker keeps its pygit2 handle and
    `repos_last_fetched` entry for a directory that no longer exists: the exact
    cache leak this series exists to close, reintroduced at every shutdown that
    lands in the window. The watcher's bounded drain did not cover this path —
    `sweep_orphans` lives in the watcher's `_tasks`, not in `_pending_purges`.

    Mutation: `await self._pubsub_endpoint.publish(...)` inline (no task, no
    shield) -> nothing is published.
    """
    import time as _time

    live = _scope("live", "https://git/live.git")
    _clone_dir_for(tmp_path, live)
    orphan = _git_sources(tmp_path) / _SID
    orphan.mkdir()
    pubsub = FakePubSubEndpoint()
    purger = LeaderScopePurger(
        base_dir=tmp_path, scopes=FakeScopeRepository([live]), pubsub_endpoint=pubsub
    )
    await purger.sweep_orphans()  # corroborate; the next pass reclaims

    state = {"in_rmtree": False}
    real_rmtree = shutil.rmtree

    def _slow_rmtree(path, *a, **kw):
        state["in_rmtree"] = True
        _time.sleep(0.3)  # on the executor thread, as in production
        return real_rmtree(path, *a, **kw)

    monkeypatch.setattr(shutil, "rmtree", _slow_rmtree)
    task = asyncio.create_task(purger.sweep_orphans())
    for _ in range(200):
        if state["in_rmtree"]:
            break
        await asyncio.sleep(0.01)
    assert state["in_rmtree"], "never reached the rmtree, so this proves nothing"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.wait_for(purger.stop(), timeout=5)  # the bounded drain

    assert not orphan.exists(), "the executor thread should have finished the rmtree"
    assert pubsub.published, (
        "the dir was deleted but no confirmation was broadcast — every other "
        "worker now holds a handle for a directory that no longer exists"
    )
    assert pubsub.published[0][1]["source_id"] == _SID
