"""The orphan sweep: the scopes leader removes the clone directories in BASE_DIR's
git_sources that no stored scope uses, two sightings an interval apart, never
more than OPAL_SCOPES_ORPHAN_SWEEP_MAX_SHARE of them, never through a symlink,
and never while a git op, a repack or a delete holds the clone.

The scope store is a fake; the clone tree is real, under tmp_path. Each guard
has a test that fails with that guard alone removed.
"""

import asyncio
import errno
import fcntl
import math
import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import pygit2
import pytest
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server import git_cli
from opal_server import git_fetcher as git_fetcher_module
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    _drop_repack_lock,
    _DueRepack,
    _fetch_mark_name,
    _mark_git_op_done,
    _mark_git_op_started,
    _repacks_due,
    _take_repack_lock,
    reclaim_clone_dir_unless_busy,
    remove_stale_fetch_marks,
    source_busy,
)
from opal_server.health import HEARTBEAT_FILE_NAME
from opal_server.scopes import orphans
from opal_server.scopes.orphans import (
    OrphanCloneSweeper,
    orphan_sweep_interval,
    orphan_sweep_max_share,
)
from opal_server.scopes.scope_repository import ScopeNotFoundError

pytestmark = pytest.mark.fetch_backend("both")

INTERVAL = 60.0


def _scope(scope_id: str, url: Optional[str] = None, branch: str = "main") -> Scope:
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git",
            url=url or f"https://git.example/{scope_id}.git",
            branch=branch,
            auth=NoAuthData(auth_type="none"),
        ),
    )


def _source_id(scope: Scope) -> str:
    return GitPolicyFetcher.source_id(scope.policy)


class FakeStore:
    """A ScopeRepository: ids() lists the keys, all() reads the records, get()
    reads one."""

    def __init__(self, scopes: Iterable[Scope] = ()) -> None:
        self.scopes: Dict[str, Scope] = {s.scope_id: s for s in scopes}
        self.not_returned: Set[str] = set()  # all() skips these records
        self.not_listed: Set[str] = set()  # ids() skips these keys
        self.error: Optional[Exception] = None
        self.get_error: Optional[Exception] = None
        self.reads: List[str] = []

    def put(self, scope: Scope) -> None:
        self.scopes[scope.scope_id] = scope

    def remove(self, scope_id: str) -> None:
        self.scopes.pop(scope_id, None)

    async def ids(self) -> List[str]:
        await asyncio.sleep(0)
        if self.error is not None:
            raise self.error
        return sorted(i for i in self.scopes if i not in self.not_listed)

    async def all(self) -> List[Scope]:
        await asyncio.sleep(0)
        if self.error is not None:
            raise self.error
        return [s for i, s in self.scopes.items() if i not in self.not_returned]

    async def get(self, scope_id: str) -> Scope:
        await asyncio.sleep(0)
        self.reads.append(scope_id)
        if self.get_error is not None:
            raise self.get_error
        if scope_id not in self.scopes:
            raise ScopeNotFoundError(scope_id)
        return self.scopes[scope_id]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(opal_server_config, "SCOPES_ORPHAN_SWEEP_INTERVAL", INTERVAL)
    monkeypatch.setattr(opal_server_config, "SCOPES_ORPHAN_SWEEP_MAX_SHARE", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [])
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 1)


@pytest.fixture(autouse=True)
def _clean_caches():
    caches = (
        GitPolicyFetcher.repos,
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.repo_locks,
        GitPolicyFetcher.pending_branches,
        GitPolicyFetcher.branch_attempts,
        GitPolicyFetcher.source_backoff,
        GitPolicyFetcher.fetch_failures,
        _repacks_due,
    )
    for cache in caches:
        cache.clear()
    yield
    for cache in caches:
        cache.clear()


@pytest.fixture(autouse=True)
def sent(monkeypatch):
    seen: List[tuple] = []
    monkeypatch.setattr(
        metrics,
        "increment",
        lambda name, tags=None: seen.append(("count", name, tags)),
    )
    monkeypatch.setattr(
        metrics,
        "gauge",
        lambda name, value, tags=None: seen.append(("gauge", name, value, tags)),
    )
    return seen


@pytest.fixture
def logs():
    lines: List[tuple] = []
    sink = logger.add(
        lambda m: lines.append((m.record["level"].name, m.record["message"])),
        level="DEBUG",
    )
    yield lines
    logger.remove(sink)


@pytest.fixture
def clones(tmp_path) -> Path:
    path = GitPolicyFetcher.base_dir(tmp_path)
    path.mkdir()
    return path


@pytest.fixture
def clock() -> Clock:
    return Clock()


def _make_clone(clones: Path, source_id: str) -> Path:
    path = clones / source_id
    (path / ".git" / "objects" / "pack").mkdir(parents=True)
    (path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (path / ".git" / "objects" / "pack" / "pack-1.pack").write_bytes(b"x" * 64)
    return path


def _sweeper(tmp_path: Path, store: FakeStore, clock: Clock, **kwargs):
    return OrphanCloneSweeper(tmp_path, store, INTERVAL, clock=clock, **kwargs)


def _on_disk(clones: Path) -> Set[str]:
    return {e.name for e in os.scandir(clones)}


async def _two_sightings(sweeper, clock: Clock):
    first = await sweeper.sweep_once()
    clock.advance(INTERVAL)
    second = await sweeper.sweep_once()
    return first, second


def _live_and_orphans(clones: Path, live: int, unused: int, prefix: str = "s"):
    """``live`` stored scopes with a clone each, and ``unused`` clones of
    scopes that are not stored."""
    scopes = [_scope(f"{prefix}-live-{i}") for i in range(live)]
    for scope in scopes:
        _make_clone(clones, _source_id(scope))
    orphaned = [_source_id(_scope(f"{prefix}-gone-{i}")) for i in range(unused)]
    for source_id in orphaned:
        _make_clone(clones, source_id)
    return FakeStore(scopes), [_source_id(s) for s in scopes], orphaned


# --- corroboration --------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unused_clone_goes_after_two_sightings_an_interval_apart(
    tmp_path, clones, clock
):
    store, live, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.outcome == "nothing" and first.removed == 0
    assert (first.counted, first.unused, first.waiting) == (2, 1, 1)
    assert second.outcome == "removed" and second.removed == 1
    assert second.waiting == 0
    assert not (clones / orphan).exists()
    assert (clones / live[0]).is_dir()


@pytest.mark.asyncio
async def test_a_second_sighting_inside_the_interval_removes_nothing(
    tmp_path, clones, clock
):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL - 0.001)

    outcome = await sweeper.sweep_once()

    assert outcome.outcome == "nothing" and outcome.removed == 0
    assert (clones / orphan).is_dir()
    clock.advance(0.001)
    assert (await sweeper.sweep_once()).removed == 1


@pytest.mark.asyncio
async def test_a_clone_seen_live_between_sightings_is_kept(tmp_path, clones, clock):
    store, _, _ = _live_and_orphans(clones, live=1, unused=0)
    comeback = _scope("comeback")
    path = _make_clone(clones, _source_id(comeback))
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()  # unused: first sighting
    clock.advance(INTERVAL / 2)
    store.put(comeback)
    await sweeper.sweep_once()  # live again
    store.remove("comeback")
    clock.advance(INTERVAL / 2)

    third = await sweeper.sweep_once()  # unused again: a first sighting

    assert third.removed == 0 and path.is_dir()
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 1
    assert not path.exists()


@pytest.mark.asyncio
async def test_a_new_sweeper_starts_over(tmp_path, clones, clock):
    """A restart or a new leader: what the old one saw is gone with it, which
    delays a removal and never hastens one."""
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    await _sweeper(tmp_path, store, clock).sweep_once()
    clock.advance(INTERVAL)

    outcome = await _sweeper(tmp_path, store, clock).sweep_once()

    assert outcome.removed == 0 and (clones / orphan).is_dir()


# --- the share guard ------------------------------------------------------------


@pytest.mark.asyncio
async def test_more_unused_than_the_max_share_is_refused(
    tmp_path, clones, clock, sent, logs
):
    store, _, orphaned = _live_and_orphans(clones, live=2, unused=3)
    sweeper = _sweeper(tmp_path, store, clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.outcome == second.outcome == "refused"
    assert (second.counted, second.unused, second.removed) == (5, 3, 0)
    assert all((clones / s).is_dir() for s in orphaned)
    assert ("count", "opal_server.scopes.orphan_sweep", {"outcome": "refused"}) in sent
    assert ("gauge", "opal_server.scopes.orphan_clone_dirs", 3, None) in sent
    assert any(level == "WARNING" and "refused" in m for level, m in logs)
    assert any(
        level == "INFO"
        and m.startswith(
            "Orphan sweep: 5 clone dirs, 3 unused, 0 removed, outcome refused"
        )
        for level, m in logs
    )


@pytest.mark.asyncio
async def test_a_share_equal_to_the_max_is_allowed(tmp_path, clones, clock):
    store, _, orphaned = _live_and_orphans(clones, live=2, unused=2)
    sweeper = _sweeper(tmp_path, store, clock)

    _, second = await _two_sightings(sweeper, clock)

    assert second.outcome == "removed" and second.removed == 2
    assert not any((clones / s).exists() for s in orphaned)


@pytest.mark.asyncio
async def test_an_empty_store_is_refused(tmp_path, clones, clock, monkeypatch):
    """A wiped store, or a server pointed at another one, looks the same as a
    store whose scopes were all deleted: nothing goes until a person raises
    the share."""
    _, live, orphaned = _live_and_orphans(clones, live=2, unused=1)
    sweeper = _sweeper(tmp_path, FakeStore(), clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.outcome == second.outcome == "refused"
    assert all((clones / s).is_dir() for s in live + orphaned)

    monkeypatch.setattr(opal_server_config, "SCOPES_ORPHAN_SWEEP_MAX_SHARE", 1.0)
    clock.advance(INTERVAL)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 3
    assert _on_disk(clones) == set()


@pytest.mark.asyncio
async def test_a_refused_sweep_forgets_its_sightings(tmp_path, clones, clock):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()  # first sighting of the orphan
    extra = [_source_id(_scope(f"extra-{i}")) for i in range(2)]
    for source_id in extra:
        _make_clone(clones, source_id)
    clock.advance(INTERVAL / 2)
    assert (await sweeper.sweep_once()).outcome == "refused"  # 3 of 4 unused
    for source_id in extra:
        shutil.rmtree(clones / source_id)
    clock.advance(INTERVAL / 2)

    after = await sweeper.sweep_once()

    assert after.outcome == "nothing" and (clones / orphan).is_dir()
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 1


@pytest.mark.asyncio
async def test_junk_names_are_not_counted(tmp_path, clones, clock):
    """Only real directories named like a clone are counted, so junk cannot buy
    headroom under the share."""
    store, live, orphaned = _live_and_orphans(clones, live=1, unused=2)
    junk = [
        "notaclone",
        "A" * 64 + "-0",  # upper-case hex
        "a" * 63 + "-0",
        "a" * 64 + "-x",
        "a" * 64 + "-0.hung",
        ".libgit2-home",
        f".{live[0]}.clone-1234",
    ]
    for name in junk:
        (clones / name).mkdir()
    (clones / ("b" * 64 + "-0")).write_text("a file, not a directory")
    (clones / f".{live[0]}.lock").write_text("")
    sweeper = _sweeper(tmp_path, store, clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.counted == 3 and first.unused == 2
    assert second.outcome == "refused"
    assert all((clones / name).is_dir() for name in junk)
    assert (clones / ("b" * 64 + "-0")).is_file()
    assert all((clones / s).is_dir() for s in orphaned)


@pytest.mark.asyncio
async def test_a_symlink_named_like_a_clone_is_never_removed_or_counted(
    tmp_path, clones, clock, logs
):
    store, _, _ = _live_and_orphans(clones, live=1, unused=0)
    target = tmp_path / "elsewhere"
    (target / ".git").mkdir(parents=True)
    (target / "keep-me").write_text("data outside the clones")
    link = clones / _source_id(_scope("linked"))
    link.symlink_to(target, target_is_directory=True)
    sweeper = _sweeper(tmp_path, store, clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.counted == second.counted == 1
    assert second.removed == 0
    assert link.is_symlink() and (target / "keep-me").is_file()
    assert any("symlink" in m for _, m in logs)


def test_the_reclaim_never_follows_a_symlink(tmp_path, clones):
    """A directory swapped for a symlink after the listing is not removed, nor
    what it points at."""
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep-me").write_text("data outside the clones")
    link = clones / ("c" * 64 + "-0")
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(NotADirectoryError):
        reclaim_clone_dir_unless_busy(str(link))

    assert link.is_symlink() and (target / "keep-me").is_file()


@pytest.mark.asyncio
async def test_the_clones_of_required_repos_are_kept(
    tmp_path, clones, clock, monkeypatch
):
    url = "https://git.example/required.git"
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [url])
    store, _, _ = _live_and_orphans(clones, live=1, unused=0)
    (required,) = GitPolicyFetcher.repo_source_ids(url)
    _make_clone(clones, required)
    sweeper = _sweeper(tmp_path, store, clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.unused == second.unused == 0
    assert (clones / required).is_dir()


@pytest.mark.fetch_backend("cli")
@pytest.mark.asyncio
async def test_the_other_shard_dirs_of_a_repository_go_with_the_git_command_line(
    tmp_path, clones, clock, monkeypatch
):
    """N1: the git command line keeps one clone per repository (shard 0), so
    libgit2's other shard dirs are used by no scope."""
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    scopes = [
        _scope(f"shard-{i}", url="https://git.example/root.git") for i in range(3)
    ]
    base = GitPolicyFetcher.repo_hash("https://git.example/root.git")
    for index in range(3):
        _make_clone(clones, f"{base}-{index}")
    others = [_scope(f"other-{i}") for i in range(2)]
    for scope in others:
        _make_clone(clones, _source_id(scope))
    sweeper = _sweeper(tmp_path, FakeStore(scopes + others), clock)

    _, second = await _two_sightings(sweeper, clock)

    assert second.removed == 2
    assert _on_disk(clones) >= {f"{base}-0"} | {_source_id(s) for s in others}
    assert not (clones / f"{base}-1").exists() and not (clones / f"{base}-2").exists()


@pytest.mark.asyncio
async def test_the_heartbeat_and_other_base_dir_files_are_never_touched(
    tmp_path, clones, clock
):
    store, _, _ = _live_and_orphans(clones, live=1, unused=1)
    heartbeat = tmp_path / HEARTBEAT_FILE_NAME
    heartbeat.write_text('{"pid": 1, "at": 0}')
    home = clones / ".libgit2-home" / ".ssh"
    home.mkdir(parents=True)
    (home / "known_hosts").write_text("host ssh-ed25519 AAAA\n")
    sweeper = _sweeper(tmp_path, store, clock)

    await _two_sightings(sweeper, clock)

    assert heartbeat.read_text() == '{"pid": 1, "at": 0}'
    assert (home / "known_hosts").read_text() == "host ssh-ed25519 AAAA\n"


# --- the store ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_store_error_decides_nothing(tmp_path, clones, clock, sent):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    store.error = ConnectionError("store down")
    clock.advance(INTERVAL)

    failed = await sweeper.sweep_once()

    assert failed.outcome == "store_error" and (clones / orphan).is_dir()
    assert failed.counted == 2
    assert (
        "count",
        "opal_server.scopes.orphan_sweep",
        {"outcome": "store_error"},
    ) in sent
    store.error = None
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 0  # sightings were forgotten
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 1


@pytest.mark.asyncio
async def test_a_record_that_does_not_parse_decides_nothing(tmp_path, clones, clock):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    store.error = ValueError("a scope record does not parse")
    clock.advance(INTERVAL)

    assert (await sweeper.sweep_once()).outcome == "store_error"
    assert (clones / orphan).is_dir()


@pytest.mark.asyncio
async def test_a_scope_listed_by_key_but_not_returned_stops_the_sweep(
    tmp_path, clones, clock, sent
):
    """ids() lists its key, all() does not return its record, and a read of
    it finds it: the listing was incomplete, so nothing is decided."""
    store, _, _ = _live_and_orphans(clones, live=1, unused=0)
    hidden = _scope("hidden")
    path = _make_clone(clones, _source_id(hidden))
    store.put(hidden)
    store.not_returned.add("hidden")
    sweeper = _sweeper(tmp_path, store, clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.outcome == second.outcome == "store_inconsistent"
    assert path.is_dir() and store.reads == ["hidden", "hidden"]
    assert (
        "count",
        "opal_server.scopes.orphan_sweep",
        {"outcome": "store_inconsistent"},
    ) in sent
    store.not_returned.clear()
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).outcome == "nothing"


@pytest.mark.asyncio
async def test_a_listed_scope_deleted_before_its_read_counts_as_deleted(
    tmp_path, clones, clock
):
    """Listed by key, gone by the time all() and the read reach it: a delete
    between the reads, not an incomplete listing."""
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)

    class DeletedBetweenReads(FakeStore):
        async def ids(self):
            return sorted(set(await super().ids()) | {"deleted-meanwhile"})

    racing = DeletedBetweenReads(store.scopes.values())
    sweeper = _sweeper(tmp_path, racing, clock)

    _, second = await _two_sightings(sweeper, clock)

    assert second.removed == 1 and not (clones / orphan).exists()
    assert racing.reads == ["deleted-meanwhile", "deleted-meanwhile"]


@pytest.mark.asyncio
async def test_a_failed_read_of_a_listed_scope_is_a_store_error(
    tmp_path, clones, clock
):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    store.put(_scope("unreadable"))
    store.not_returned.add("unreadable")
    store.get_error = TimeoutError("read timed out")
    sweeper = _sweeper(tmp_path, store, clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.outcome == second.outcome == "store_error"
    assert (clones / orphan).is_dir()


@pytest.mark.asyncio
async def test_many_listed_scopes_not_returned_stop_the_sweep_without_reads(
    tmp_path, clones, clock
):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    for i in range(orphans._MAX_LISTING_GAP_READS + 1):
        store.put(_scope(f"gap-{i}"))
        store.not_returned.add(f"gap-{i}")
    sweeper = _sweeper(tmp_path, store, clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.outcome == second.outcome == "store_inconsistent"
    assert store.reads == [] and (clones / orphan).is_dir()


@pytest.mark.asyncio
async def test_an_evicted_record_counts_as_deleted_after_two_sightings(
    tmp_path, clones, clock
):
    """A record gone from the store (evicted, lost in a restore) is listed by
    neither ids() nor all(): its clone goes like a deleted scope's."""
    store, _, _ = _live_and_orphans(clones, live=1, unused=0)
    evicted = _scope("evicted")
    path = _make_clone(clones, _source_id(evicted))
    store.put(evicted)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    store.remove("evicted")
    clock.advance(INTERVAL)

    assert (await sweeper.sweep_once()).removed == 0  # first unused sighting
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 1
    assert not path.exists()


@pytest.mark.asyncio
async def test_a_missing_clones_dir_is_nothing_and_an_unreadable_one_decides_nothing(
    tmp_path, clock, sent, monkeypatch
):
    store = FakeStore([_scope("live")])
    sweeper = _sweeper(tmp_path, store, clock)
    assert (await sweeper.sweep_once()).outcome == "nothing"  # no git_sources yet

    clones = GitPolicyFetcher.base_dir(tmp_path)
    clones.mkdir()
    _make_clone(clones, _source_id(_scope("live")))
    orphan = _make_clone(clones, _source_id(_scope("gone")))
    await sweeper.sweep_once()
    real_scandir = os.scandir

    def unreadable(path=".", *args):
        if isinstance(path, (str, os.PathLike)) and Path(path) == clones:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return real_scandir(path, *args)

    monkeypatch.setattr(orphans.os, "scandir", unreadable)
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).outcome == "disk_error"
    monkeypatch.setattr(orphans.os, "scandir", real_scandir)
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 0  # sightings were forgotten
    assert orphan.is_dir()
    assert (
        "count",
        "opal_server.scopes.orphan_sweep",
        {"outcome": "disk_error"},
    ) in sent


# --- living with live ops -------------------------------------------------------


@pytest.mark.asyncio
async def test_a_busy_lock_source_skips_the_clone(tmp_path, clones, clock):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)
    held, release = asyncio.Event(), asyncio.Event()

    async def hold():
        async with GitPolicyFetcher.lock_source(orphan):
            held.set()
            await release.wait()

    holder = asyncio.create_task(hold())
    await held.wait()
    try:
        busy = await sweeper.sweep_once()
    finally:
        release.set()
        await holder

    assert busy.removed == 0 and busy.busy == 1 and (clones / orphan).is_dir()
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 1


@pytest.mark.asyncio
async def test_a_lock_source_with_a_task_queued_for_it_is_busy():
    """Released with a task still queued for it, the lock is busy: the queued
    task takes it next.

    A waiter that was cancelled does not count. (Checked
    on source_busy itself: the look's own awaits let the waiter run.)
    """
    source_id = "1" * 64 + "-0"
    lock = GitPolicyFetcher.repo_locks.setdefault(source_id, asyncio.Lock())
    await lock.acquire()
    waiter = asyncio.create_task(lock.acquire())
    await asyncio.sleep(0)
    lock.release()  # the waiter is woken, but has not run yet

    assert not lock.locked() and source_busy(source_id)

    await waiter
    cancelled = asyncio.create_task(lock.acquire())
    await asyncio.sleep(0)
    cancelled.cancel()  # its wait is cancelled; it has not run since
    lock.release()

    assert not source_busy(source_id)
    await asyncio.gather(cancelled, return_exceptions=True)


@pytest.mark.asyncio
async def test_an_in_flight_git_op_skips_the_clone(tmp_path, clones, clock):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)
    _mark_git_op_started(orphan)
    try:
        busy = await sweeper.sweep_once()
    finally:
        _mark_git_op_done(orphan)

    assert busy.removed == 0 and busy.busy == 1 and (clones / orphan).is_dir()


@pytest.mark.asyncio
async def test_a_held_repack_lock_skips_the_clone(tmp_path, clones, clock):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)
    fd = _take_repack_lock(clones)
    assert fd is not None
    try:
        busy = await sweeper.sweep_once()
    finally:
        _drop_repack_lock(fd)

    assert busy.removed == 0 and busy.busy == 1 and (clones / orphan).is_dir()
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 1


@pytest.mark.asyncio
async def test_a_held_clone_lock_skips_the_clone(tmp_path, clones, clock):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)
    fd = git_cli.take_clone_lock(clones / orphan)
    assert fd is not None
    try:
        busy = await sweeper.sweep_once()
    finally:
        git_cli.drop_clone_lock(fd)

    assert busy.removed == 0 and busy.busy == 1 and (clones / orphan).is_dir()
    assert git_cli.clone_lock_path(clones / orphan).exists()


@pytest.mark.parametrize("which", ["repack", "clone"])
@pytest.mark.asyncio
async def test_a_lock_that_cannot_be_taken_keeps_the_clone_and_backs_off(
    tmp_path, clones, clock, monkeypatch, which, logs
):
    """Flock failing (ENOLCK, an NFS mount without local_lock=flock): never
    removed without its locks, with the git command-line fetch on or off."""
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)
    real_flock = fcntl.flock
    clones_ino = os.stat(clones).st_ino

    def failing(fd, op):
        is_repack = os.fstat(fd).st_ino == clones_ino
        if is_repack == (which == "repack"):
            raise OSError(errno.ENOLCK, "No locks available")
        return real_flock(fd, op)

    monkeypatch.setattr(fcntl, "flock", failing)

    failed = await sweeper.sweep_once()

    assert failed.removed == 0 and failed.failed == 1
    assert (clones / orphan).is_dir()
    assert any(level == "WARNING" and orphan in m for level, m in logs)
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).failed == 1  # retried after one interval
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).failed == 0  # now waits two
    monkeypatch.setattr(fcntl, "flock", real_flock)
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 1


@pytest.mark.asyncio
async def test_a_failed_removal_backs_off_doubling_from_the_interval(
    tmp_path, clones, clock, monkeypatch
):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    real_rmtree = shutil.rmtree
    attempts: List[float] = []

    def failing(path, *args, **kwargs):
        if Path(path).name == orphan:
            attempts.append(clock.now)
            raise PermissionError(errno.EPERM, "Operation not permitted", str(path))
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", failing)
    for _ in range(8):
        clock.advance(INTERVAL)
        await sweeper.sweep_once()

    start = attempts[0]
    assert [round((a - start) / INTERVAL) for a in attempts] == [0, 1, 3, 7]
    assert (clones / orphan).is_dir()


@pytest.mark.asyncio
async def test_a_clone_in_backoff_does_not_use_the_budget(
    tmp_path, clones, clock, monkeypatch
):
    store, _, (stuck,) = _live_and_orphans(clones, live=20, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    real_rmtree = shutil.rmtree

    def failing(path, *args, **kwargs):
        if Path(path).name == stuck:
            raise PermissionError(errno.EPERM, "Operation not permitted", str(path))
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", failing)
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).failed == 1  # retried after one interval
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).failed == 1  # then after two
    others = [_source_id(_scope(f"other-gone-{i}")) for i in range(16)]
    for source_id in others:
        _make_clone(clones, source_id)
    await sweeper.sweep_once()  # the others' first sighting
    clock.advance(INTERVAL)

    in_backoff = await sweeper.sweep_once()

    assert (in_backoff.removed, in_backoff.failed) == (16, 0)
    assert (clones / stuck).is_dir()
    assert not any((clones / s).exists() for s in others)


@pytest.mark.asyncio
async def test_at_most_16_removals_per_sweep_the_longest_unused_first(
    tmp_path, clones, clock
):
    store, _, older = _live_and_orphans(clones, live=20, unused=8, prefix="a")
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL / 2)
    newer = [_source_id(_scope(f"b-gone-{i}")) for i in range(12)]
    for source_id in newer:
        _make_clone(clones, source_id)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)

    capped = await sweeper.sweep_once()

    assert capped.removed == 16
    assert not any((clones / s).exists() for s in older)
    assert sum((clones / s).exists() for s in newer) == 4
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).removed == 4


@pytest.mark.asyncio
async def test_a_clone_removed_by_someone_else_meanwhile_is_not_counted(
    tmp_path, clones, clock, monkeypatch
):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)
    real = git_fetcher_module.reclaim_clone_dir_unless_busy

    def removed_first(path):
        shutil.rmtree(path)  # the DELETE floor of another worker, say
        return real(path)

    monkeypatch.setattr(orphans, "reclaim_clone_dir_unless_busy", removed_first)

    outcome = await sweeper.sweep_once()

    assert outcome.removed == 0 and outcome.failed == 0
    assert outcome.outcome == "nothing"


# --- what goes with a clone, and the caches -------------------------------------


@pytest.mark.asyncio
async def test_hung_markers_clone_dirs_host_keys_and_lock_file_go_with_the_clone(
    tmp_path, clones, clock
):
    store, live, (orphan,) = _live_and_orphans(clones, live=1, unused=1)

    def beside(source_id: str) -> List[Path]:
        markers = clones / f"{source_id}.hung"
        markers.mkdir()
        (markers / "host-1-0-abcd").write_text("")
        clone_dir = clones / f".{source_id}.clone-x1y2"
        (clone_dir / ".git").mkdir(parents=True)
        host_keys = clones / f".{source_id}.known_hosts"
        host_keys.write_text("git.example ssh-ed25519 AAAA\n")
        lock = git_cli.clone_lock_path(clones / source_id)
        lock.write_text("")
        return [markers, clone_dir, host_keys, lock]

    orphan_beside = beside(orphan)
    live_beside = beside(live[0])
    sweeper = _sweeper(tmp_path, store, clock)

    await _two_sightings(sweeper, clock)

    assert not any(p.exists() for p in orphan_beside)
    assert all(p.exists() for p in live_beside)


@pytest.mark.asyncio
async def test_the_reclaim_drops_this_process_s_caches_of_the_clone(
    tmp_path, clones, clock
):
    store, live, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    freed: List[str] = []

    class Handle:
        def __init__(self, name):
            self._name = name

        def free(self):
            freed.append(self._name)

    for source_id in (orphan, live[0]):
        path = str(clones / source_id)
        GitPolicyFetcher.repos[path] = Handle(source_id)
        GitPolicyFetcher.repos_last_fetched[source_id] = object()
        GitPolicyFetcher.pending_branches[source_id] = {"main"}
        GitPolicyFetcher.fetch_failures[source_id] = 3
        _repacks_due[source_id] = _DueRepack(
            source_id=source_id, repo_path=path, scope_id="s", url="u"
        )
    sweeper = _sweeper(tmp_path, store, clock)

    await _two_sightings(sweeper, clock)

    assert freed == [orphan]
    for cache in (
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.pending_branches,
        GitPolicyFetcher.fetch_failures,
        _repacks_due,
    ):
        assert orphan not in cache and live[0] in cache
    assert str(clones / live[0]) in GitPolicyFetcher.repos


@pytest.mark.asyncio
async def test_the_repo_locks_entry_is_popped_on_every_exit(
    tmp_path, clones, clock, monkeypatch
):
    """Invariant I4: no repo_locks entry is left for a source no scope uses,
    whether the clone went, was busy in another process, or failed."""
    store, _, orphaned = _live_and_orphans(clones, live=3, unused=3)
    removed, busy, failing = sorted(orphaned)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    real_rmtree = shutil.rmtree

    def rmtree(path, *args, **kwargs):
        if Path(path).name == failing:
            raise PermissionError(errno.EPERM, "Operation not permitted", str(path))
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", rmtree)
    fd = git_cli.take_clone_lock(clones / busy)
    clock.advance(INTERVAL)
    try:
        outcome = await sweeper.sweep_once()
    finally:
        git_cli.drop_clone_lock(fd)

    assert (outcome.removed, outcome.busy, outcome.failed) == (1, 1, 1)
    assert not set(orphaned) & set(GitPolicyFetcher.repo_locks)


@pytest.mark.asyncio
async def test_a_live_sibling_s_lock_entry_survives(tmp_path, clones, clock):
    store, live, _ = _live_and_orphans(clones, live=1, unused=1)
    lock = GitPolicyFetcher.repo_locks.setdefault(live[0], asyncio.Lock())
    sweeper = _sweeper(tmp_path, store, clock)

    await _two_sightings(sweeper, clock)

    assert GitPolicyFetcher.repo_locks.get(live[0]) is lock


def test_reclaim_says_whether_it_removed_was_busy_or_found_nothing(tmp_path, clones):
    path = _make_clone(clones, "d" * 64 + "-0")
    fd = git_cli.take_clone_lock(path)
    try:
        assert reclaim_clone_dir_unless_busy(str(path)) is False
    finally:
        git_cli.drop_clone_lock(fd)
    assert path.is_dir()

    assert reclaim_clone_dir_unless_busy(str(path)) is True
    assert not path.exists() and not git_cli.clone_lock_path(path).exists()

    assert reclaim_clone_dir_unless_busy(str(path)) is None
    assert not git_cli.clone_lock_path(path).exists()


def test_a_lock_file_that_cannot_be_unlinked_is_logged_and_the_clone_still_goes(
    tmp_path, clones, monkeypatch, logs
):
    path = _make_clone(clones, "e" * 64 + "-0")
    lock = git_cli.clone_lock_path(path)
    real_unlink = Path.unlink

    def unlink(self, missing_ok=False):
        if self == lock:
            raise PermissionError(errno.EACCES, "Permission denied", str(self))
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)

    assert reclaim_clone_dir_unless_busy(str(path)) is True

    assert not path.exists() and lock.exists()
    assert any(level == "WARNING" and str(lock) in m for level, m in logs)


# --- fetch marks ----------------------------------------------------------------


def _marks(clone: Path) -> Path:
    marks = clone / ".git" / "opal-fetched"
    marks.mkdir(exist_ok=True)
    return marks


def _mark(marks: Path, name: str, mtime: float) -> Path:
    path = marks / name
    path.write_text("")
    os.utime(path, (mtime, mtime))
    return path


@pytest.mark.asyncio
async def test_stale_fetch_marks_go_and_the_others_stay(tmp_path, clones, clock):
    """G3a's marks: one file per branch ever fetched.

    The sweep removes the marks of branches no stored scope of the clone
    tracks, dated before it read the store; a fetch that started after
    that may be for a scope the read missed.
    """
    url = "https://git.example/shared.git"
    scopes = [_scope("a", url=url, branch="main"), _scope("b", url=url, branch="dev")]
    clone = _make_clone(clones, _source_id(scopes[0]))
    marks = _marks(clone)
    listed_at = 5_000_000.0
    old = listed_at - 100
    kept = [
        _mark(marks, _fetch_mark_name("main"), old),
        _mark(marks, _fetch_mark_name("dev"), old),
        _mark(marks, "ALL", old),
        _mark(marks, "FAILED", old),
        _mark(marks, f".{_fetch_mark_name('gone')}.ab12cd34", old),  # a temp name
        _mark(marks, "README", old),
        _mark(marks, _fetch_mark_name("brand-new"), listed_at),
    ]
    gone = [_mark(marks, _fetch_mark_name(f"deleted-{i}"), old) for i in range(3)]
    sweeper = _sweeper(tmp_path, FakeStore(scopes), clock, wall_clock=lambda: listed_at)

    outcome = await sweeper.sweep_once()

    assert outcome.marks_removed == 3
    assert all(p.exists() for p in kept) and not any(p.exists() for p in gone)


@pytest.mark.asyncio
async def test_fetch_marks_of_a_busy_clone_are_left(tmp_path, clones, clock):
    scope = _scope("a")
    clone = _make_clone(clones, _source_id(scope))
    stale = _mark(_marks(clone), _fetch_mark_name("gone"), 1.0)
    sweeper = _sweeper(tmp_path, FakeStore([scope]), clock)
    _mark_git_op_started(_source_id(scope))
    try:
        busy = await sweeper.sweep_once()
    finally:
        _mark_git_op_done(_source_id(scope))
    assert busy.marks_removed == 0 and stale.exists()

    held, release = asyncio.Event(), asyncio.Event()

    async def hold():
        async with GitPolicyFetcher.lock_source(_source_id(scope)):
            held.set()
            await release.wait()

    holder = asyncio.create_task(hold())
    await held.wait()
    try:
        locked = await sweeper.sweep_once()
    finally:
        release.set()
        await holder
    assert locked.marks_removed == 0 and stale.exists()
    GitPolicyFetcher.repo_locks.clear()  # the holder's

    assert (await sweeper.sweep_once()).marks_removed == 1
    assert _source_id(scope) not in GitPolicyFetcher.repo_locks  # none minted


@pytest.mark.asyncio
async def test_no_fetch_mark_goes_when_the_sweep_decides_nothing(
    tmp_path, clones, clock
):
    scope = _scope("a")
    clone = _make_clone(clones, _source_id(scope))
    stale = _mark(_marks(clone), _fetch_mark_name("gone"), 1.0)
    for i in range(2):
        _make_clone(clones, _source_id(_scope(f"gone-{i}")))
    sweeper = _sweeper(tmp_path, FakeStore([scope]), clock)

    assert (await sweeper.sweep_once()).outcome == "refused"
    assert stale.exists()


def test_fetch_marks_through_a_symlink_are_left(tmp_path, clones):
    clone = _make_clone(clones, "f" * 64 + "-0")
    outside = tmp_path / "outside"
    outside.mkdir()
    stale = _mark(outside, _fetch_mark_name("gone"), 1.0)
    (clone / ".git" / "opal-fetched").symlink_to(outside, target_is_directory=True)

    assert remove_stale_fetch_marks(clone, set(), 1e12) == 0
    assert stale.exists()


def test_no_marks_directory_removes_nothing(tmp_path, clones):
    clone = _make_clone(clones, "f" * 64 + "-1")
    assert remove_stale_fetch_marks(clone, {"main"}, 1e12) == 0


# --- metrics, the heartbeat line, the settings, the task ------------------------


@pytest.mark.asyncio
async def test_metrics_and_the_heartbeat_line_name_the_outcome(
    tmp_path, clones, clock, sent, logs
):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)

    await _two_sightings(sweeper, clock)

    assert (
        sent.count(("count", "opal_server.scopes.orphan_sweep", {"outcome": "nothing"}))
        == 1
    )
    assert (
        sent.count(("count", "opal_server.scopes.orphan_sweep", {"outcome": "removed"}))
        == 1
    )
    assert sent.count(("count", "opal_server.scopes.orphan_clone_removed", None)) == 1
    assert ("gauge", "opal_server.scopes.orphan_clone_dirs", 1, None) in sent
    heartbeats = [
        m for level, m in logs if level == "INFO" and m.startswith("Orphan sweep: ")
    ]
    assert heartbeats[0].startswith(
        "Orphan sweep: 2 clone dirs, 1 unused, 0 removed, outcome nothing"
    )
    assert heartbeats[-1].startswith(
        "Orphan sweep: 2 clone dirs, 1 unused, 1 removed, outcome removed"
    )
    assert any(orphan in m and "removed" in m for level, m in logs if level == "INFO")
    assert not any("https://" in m for _, m in logs)


@pytest.mark.asyncio
async def test_a_failed_removal_is_counted(tmp_path, clones, clock, sent, monkeypatch):
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    monkeypatch.setattr(
        orphans,
        "reclaim_clone_dir_unless_busy",
        lambda path: (_ for _ in ()).throw(PermissionError(errno.EPERM, "no")),
    )
    clock.advance(INTERVAL)

    await sweeper.sweep_once()

    assert ("count", "opal_server.scopes.orphan_clone_remove_failed", None) in sent


@pytest.mark.parametrize(
    "value, expected",
    [(0.0, 0.0), (-5.0, 0.0), (math.nan, 0.0), (math.inf, 0.0), (30.0, 30.0)],
)
def test_the_interval_reads_off_unless_positive_and_finite(
    monkeypatch, value, expected
):
    monkeypatch.setattr(opal_server_config, "SCOPES_ORPHAN_SWEEP_INTERVAL", value)
    assert orphan_sweep_interval() == expected


@pytest.mark.parametrize(
    "value, expected",
    [(0.5, 0.5), (-1.0, 0.0), (2.0, 1.0), (math.nan, 0.0), (math.inf, 1.0)],
)
def test_the_max_share_is_clamped_and_nan_refuses(monkeypatch, value, expected):
    monkeypatch.setattr(opal_server_config, "SCOPES_ORPHAN_SWEEP_MAX_SHARE", value)
    assert orphan_sweep_max_share() == expected


def test_the_settings_default_to_off_and_half():
    from opal_server.config import OpalServerConfig

    defaults = OpalServerConfig(prefix="OPAL_TEST_DEFAULTS_NOT_SET_")
    assert defaults.SCOPES_ORPHAN_SWEEP_INTERVAL == 0.0
    assert defaults.SCOPES_ORPHAN_SWEEP_MAX_SHARE == 0.5


@pytest.mark.asyncio
async def test_run_waits_a_whole_interval_between_sweeps(tmp_path, monkeypatch):
    """The first sweep runs one interval after the start, and each one after a
    full interval more, by the clock the sightings are dated with."""
    times: List[float] = []
    loop = asyncio.get_running_loop()

    class Recording(OrphanCloneSweeper):
        async def sweep_once(self):
            times.append(loop.time())
            if len(times) == 3:
                raise asyncio.CancelledError
            return None

    sweeper = Recording(tmp_path, FakeStore(), 0.05, clock=loop.time)
    started = loop.time()
    with pytest.raises(asyncio.CancelledError):
        await sweeper.run()

    gaps = [b - a for a, b in zip([started] + times, times)]
    assert all(gap >= 0.05 for gap in gaps)


@pytest.mark.asyncio
async def test_run_survives_a_sweep_that_raises(tmp_path, logs):
    loop = asyncio.get_running_loop()
    calls: List[int] = []

    class Raising(OrphanCloneSweeper):
        async def sweep_once(self):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("a bug")
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await Raising(tmp_path, FakeStore(), 0.01, clock=loop.time).run()

    assert len(calls) == 2
    assert any(level == "ERROR" and "Orphan sweep" in m for level, m in logs)


@pytest.mark.parametrize("interval", [0.0, 0.05])
@pytest.mark.asyncio
async def test_the_leader_runs_the_sweep_only_when_it_is_on(
    tmp_path, monkeypatch, interval
):
    from opal_server.policy.watcher.task import BasePolicyWatcherTask
    from opal_server.scopes import task as task_module
    from opal_server.scopes.task import ScopesPolicyWatcherTask, _SyncPassQueue

    async def _noop_start(self):
        return None

    monkeypatch.setattr(BasePolicyWatcherTask, "start", _noop_start)
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0)
    monkeypatch.setattr(opal_server_config, "SCOPES_ORPHAN_SWEEP_INTERVAL", interval)
    sweeps: List[Path] = []

    async def sweep_once(self):
        sweeps.append(self._clones)

    monkeypatch.setattr(task_module.OrphanCloneSweeper, "sweep_once", sweep_once)

    class Notifier:
        def gen_subscriber_id(self):
            return "sub"

        async def subscribe(self, *args):
            return None

    class Endpoint:
        notifier = Notifier()
        broadcaster = None

    class Service:
        async def sync_scopes(self, *a, **k):
            return None

        async def handle(self, *a, **k):  # the purge-channel subscriber
            return None

    t = ScopesPolicyWatcherTask.__new__(ScopesPolicyWatcherTask)
    t._pubsub_endpoint = Endpoint()
    t._purger = Service()
    t._service = Service()
    t._scopes = FakeStore()
    t._tasks = []
    t._purger_sub_id = None
    t._passes = _SyncPassQueue(t._run_pass)
    t._remove_gap_listener = None
    await t.start()
    try:
        await asyncio.sleep(0.2)
    finally:
        for task in t._tasks:
            task.cancel()
        await asyncio.gather(*t._tasks, return_exceptions=True)

    if interval:
        assert sweeps and set(sweeps) == {GitPolicyFetcher.base_dir(tmp_path)}
    else:
        assert sweeps == []


# --- the store read again before each removal (a scope that came back) ---------


class _Repointing(FakeStore):
    """All() returns what its scan read, and, once armed, the scope ``back`` is
    stored (a PUT repointing it onto the orphan clone, or creating it there)
    right after the scan passed its key."""

    def __init__(self, scopes, back):
        super().__init__(scopes)
        self.back = back
        self.armed = False

    async def all(self):
        snapshot = await super().all()
        if self.armed:
            self.armed = False
            self.put(self.back)
        return snapshot


@pytest.mark.asyncio
async def test_a_scope_repointed_onto_an_orphan_during_the_look_keeps_it(
    tmp_path, clones, clock, logs
):
    live = _scope("live")
    _make_clone(clones, _source_id(live))
    away = _scope("s", url="https://git.example/elsewhere.git")
    back = _scope("s", url="https://git.example/old-home.git")
    path = _make_clone(clones, _source_id(back))
    store = _Repointing([live, away], back)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)
    store.armed = True

    second = await sweeper.sweep_once()

    assert second.removed == 0 and second.used_again == 1
    assert path.is_dir()
    assert any("used by scope s" in m for _, m in logs)
    clock.advance(INTERVAL)
    assert (await sweeper.sweep_once()).unused == 0


@pytest.mark.asyncio
async def test_a_scope_stored_on_an_orphan_while_an_earlier_one_goes_keeps_it(
    tmp_path, clones, clock, monkeypatch
):
    store, _, orphaned = _live_and_orphans(clones, live=2, unused=2)
    first, second_orphan = sorted(orphaned)
    comeback = next(
        _scope("comeback", url=f"https://git.example/s-gone-{i}.git")
        for i in range(2)
        if _source_id(_scope("x", url=f"https://git.example/s-gone-{i}.git"))
        == second_orphan
    )
    real = orphans.reclaim_clone_dir_unless_busy
    calls: List[str] = []

    def reclaim(path):
        calls.append(path)
        if len(calls) == 1:
            store.put(comeback)  # while the first rmtree runs
        return real(path)

    monkeypatch.setattr(orphans, "reclaim_clone_dir_unless_busy", reclaim)
    sweeper = _sweeper(tmp_path, store, clock)

    _, outcome = await _two_sightings(sweeper, clock)

    assert calls == [str(clones / first)]
    assert (outcome.removed, outcome.used_again) == (1, 1)
    assert (clones / second_orphan).is_dir() and not (clones / first).exists()


def _write_scope_ref(clone: Path, scope_id: str, *, packed: bool) -> None:
    name = f"scopes/{scope_id}"
    if not pygit2.reference_is_valid_name(f"refs/heads/{name}"):
        name = f"scopes/{scope_id.encode().hex()}"
    if packed:
        with open(clone / ".git" / "packed-refs", "a") as f:
            f.write(f"{'1' * 40} refs/heads/{name}\n")
        return
    ref = clone / ".git" / "refs" / "heads" / name
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text("1" * 40 + "\n")


@pytest.mark.parametrize("packed", [False, True], ids=["loose", "packed"])
@pytest.mark.parametrize("scope_id", ["hidden", "hidden one"], ids=["plain", "hex"])
@pytest.mark.asyncio
async def test_a_scope_the_listings_miss_but_the_clone_s_branch_names_stops_the_look(
    tmp_path, clones, clock, sent, packed, scope_id
):
    """Listed by neither ids() nor all(), yet stored: a get() of the scope id
    the clone's own branch names finds it, so the listing is incomplete."""
    store, _, _ = _live_and_orphans(clones, live=1, unused=0)
    hidden = _scope(scope_id)
    path = _make_clone(clones, _source_id(hidden))
    _write_scope_ref(path, scope_id, packed=packed)
    store.put(hidden)
    store.not_listed.add(scope_id)
    store.not_returned.add(scope_id)
    sweeper = _sweeper(tmp_path, store, clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.outcome == "nothing"
    assert second.outcome == "store_inconsistent" and second.removed == 0
    assert path.is_dir() and scope_id in store.reads
    assert not GitPolicyFetcher.repo_locks


@pytest.mark.asyncio
async def test_branches_of_scopes_deleted_or_moved_elsewhere_do_not_keep_a_clone(
    tmp_path, clones, clock
):
    live = _scope("live")
    _make_clone(clones, _source_id(live))
    moved = _scope("moved", url="https://git.example/new-home.git")
    _make_clone(clones, _source_id(moved))
    orphan = _make_clone(clones, _source_id(_scope("gone")))
    for scope_id in ("gone", "moved"):
        _write_scope_ref(orphan, scope_id, packed=scope_id == "moved")
    store = FakeStore([live, moved])
    sweeper = _sweeper(tmp_path, store, clock)

    _, second = await _two_sightings(sweeper, clock)

    assert second.removed == 1 and not orphan.exists()
    assert store.reads == ["gone"]  # moved's record came with the fresh listing


@pytest.mark.asyncio
async def test_a_store_error_before_a_removal_keeps_the_clone(
    tmp_path, clones, clock, monkeypatch
):
    """The read before the second removal fails: that clone stays, the look
    stops as store_error, and it still reports the removal it made."""
    store, _, orphaned = _live_and_orphans(clones, live=2, unused=2)
    first, second = sorted(orphaned)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)
    reads = 0
    real_all = store.all

    async def failing_third_read():
        nonlocal reads
        reads += 1
        if reads == 3:
            raise ConnectionError("store down")
        return await real_all()

    monkeypatch.setattr(store, "all", failing_third_read)

    outcome = await sweeper.sweep_once()

    assert outcome.outcome == "store_error"
    assert (outcome.counted, outcome.unused, outcome.removed) == (4, 2, 1)
    assert not (clones / first).exists() and (clones / second).is_dir()
    assert not GitPolicyFetcher.repo_locks


@pytest.mark.asyncio
async def test_the_read_before_a_removal_is_bounded_by_the_store_read_timeout(
    tmp_path, clones, clock, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_STORE_READ_TIMEOUT", 0.05)
    store, _, (orphan,) = _live_and_orphans(clones, live=1, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    clock.advance(INTERVAL)
    reads = 0
    real_all = store.all

    async def hanging_second_read():
        nonlocal reads
        reads += 1
        if reads == 2:
            await asyncio.sleep(3600)
        return await real_all()

    monkeypatch.setattr(store, "all", hanging_second_read)

    outcome = await asyncio.wait_for(sweeper.sweep_once(), timeout=5)

    assert outcome.outcome == "store_error" and (clones / orphan).is_dir()
    assert not GitPolicyFetcher.repo_locks


# --- required clones and a wiped store ------------------------------------------


@pytest.mark.parametrize("required, others", [(1, 1), (2, 2), (3, 1)])
@pytest.mark.asyncio
async def test_a_wiped_store_is_refused_whatever_the_required_clones(
    tmp_path, clones, clock, monkeypatch, required, others
):
    urls = [f"https://git.example/required-{i}.git" for i in range(required)]
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", urls)
    for url in urls:
        for source_id in GitPolicyFetcher.repo_source_ids(url):
            _make_clone(clones, source_id)
    tenants = [_source_id(_scope(f"tenant-{i}")) for i in range(others)]
    for source_id in tenants:
        _make_clone(clones, source_id)
    sweeper = _sweeper(tmp_path, FakeStore(), clock)

    first, second = await _two_sightings(sweeper, clock)

    assert first.outcome == second.outcome == "refused"
    assert all((clones / s).is_dir() for s in tenants)


@pytest.mark.asyncio
async def test_a_wiped_store_with_only_required_clones_is_refused(
    tmp_path, clones, clock, monkeypatch
):
    url = "https://git.example/required.git"
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [url])
    (required,) = GitPolicyFetcher.repo_source_ids(url)
    _make_clone(clones, required)

    outcome = await _sweeper(tmp_path, FakeStore(), clock).sweep_once()

    assert outcome.outcome == "refused" and (clones / required).is_dir()


@pytest.mark.asyncio
async def test_required_clones_count_on_neither_side_of_the_share(
    tmp_path, clones, clock, monkeypatch
):
    urls = [f"https://git.example/required-{i}.git" for i in range(3)]
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", urls)
    for url in urls:
        _make_clone(clones, GitPolicyFetcher.repo_source_ids(url)[0])
    store, _, orphaned = _live_and_orphans(clones, live=1, unused=2)

    refused = await _sweeper(tmp_path, store, clock).sweep_once()  # 2 of 3, not 2 of 6

    assert refused.outcome == "refused"
    shutil.rmtree(clones / orphaned[0])
    sweeper = _sweeper(tmp_path, store, clock)
    _, allowed = await _two_sightings(sweeper, clock)  # 1 of 2
    assert allowed.removed == 1


# --- after a refusal: a store being refilled -------------------------------------


def _refilling(clones: Path, total: int):
    scopes = [_scope(f"r-{i}") for i in range(total)]
    for scope in scopes:
        _make_clone(clones, _source_id(scope))
    return scopes, FakeStore()


@pytest.mark.asyncio
async def test_after_a_refusal_a_store_being_refilled_loses_no_clone(
    tmp_path, clones, clock
):
    scopes, store = _refilling(clones, 10)
    sweeper = _sweeper(tmp_path, store, clock)
    outcomes = []
    for restored in (2, 5, 8, 10, 10):
        for scope in scopes[:restored]:
            store.put(scope)
        outcomes.append(await sweeper.sweep_once())
        clock.advance(INTERVAL)

    assert outcomes[0].outcome == "refused"
    assert sum(o.removed for o in outcomes) == 0
    assert all((clones / _source_id(s)).is_dir() for s in scopes)


@pytest.mark.asyncio
async def test_after_a_refusal_two_looks_with_the_store_not_growing_remove(
    tmp_path, clones, clock
):
    scopes, store = _refilling(clones, 10)
    sweeper = _sweeper(tmp_path, store, clock)
    removed = []
    for restored in (2, 5, 5):
        for scope in scopes[:restored]:
            store.put(scope)
        removed.append((await sweeper.sweep_once()).removed)
        clock.advance(INTERVAL)

    assert removed == [0, 0, 5]


@pytest.mark.asyncio
async def test_with_no_refusal_a_growing_store_still_reclaims(tmp_path, clones, clock):
    store, _, (orphan,) = _live_and_orphans(clones, live=2, unused=1)
    sweeper = _sweeper(tmp_path, store, clock)
    await sweeper.sweep_once()
    newcomer = _scope("newcomer")
    _make_clone(clones, _source_id(newcomer))
    store.put(newcomer)
    clock.advance(INTERVAL)

    assert (await sweeper.sweep_once()).removed == 1
    assert not (clones / orphan).exists()


@pytest.mark.asyncio
async def test_once_the_store_stopped_growing_a_growing_store_reclaims_again(
    tmp_path, clones, clock
):
    """The refill rule ends with the first pair of looks that found the store
    no bigger: later growth no longer holds removals back."""
    scopes, store = _refilling(clones, 4)
    sweeper = _sweeper(tmp_path, store, clock)
    for restored in (0, 4, 4):  # refused, then two looks no bigger
        for scope in scopes[:restored]:
            store.put(scope)
        await sweeper.sweep_once()
        clock.advance(INTERVAL)
    orphan = _make_clone(clones, _source_id(_scope("late-gone")))
    removed = []
    for i in range(2):
        newcomer = _scope(f"newcomer-{i}")
        _make_clone(clones, _source_id(newcomer))
        store.put(newcomer)
        removed.append((await sweeper.sweep_once()).removed)
        clock.advance(INTERVAL)

    assert removed == [0, 1] and not orphan.exists()
