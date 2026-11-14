"""The orphan sweep beside what else removes or walks scope clones: real syncs
of live scopes (git command line and libgit2), the DELETE floor, ops taking a
clone's lock while the sweep unlinks it, the reflog removal thread (the one
remover that runs outside every lock), and the walks of git_sources that the
bundle route, the fetch metrics and readiness run.

The other removers and walks of a clone hold its lock, which the sweep's
removal takes without waiting, so they never run beside it: invalid-repo
recovery and a clone's wipe (_rmtree_unless_locked), the repack's leftover
and pack walks (_remove_repack_leftovers, the pack and ref counters, under
both locks), remove_kill_leftovers and _remove_clone_dirs (git ops, under the
clone lock), and the pre-fork preload's sweep_clone_leftovers and
_reclone_hung_under_lock (before any worker, so before any sweep).

Real git against local origins, real trees under tmp_path.
"""

import asyncio
import shutil
import threading
from pathlib import Path
from typing import List

import git
import pygit2
import pytest
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server import git_cli, git_fetcher
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    clone_landed,
    fetch_mark_after,
    reclaim_clone_dir_unless_busy,
    remove_clone_dir_exclusive,
)
from opal_server.health import emit_repo_fetch_metrics
from opal_server.scopes.orphans import OrphanCloneSweeper
from opal_server.scopes.readiness import RequiredClonesLatch
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService

pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="needs git"),
    pytest.mark.fetch_backend("both"),
]

_AUTHOR = git.Actor("test", "test@example.com")


class _Store:
    def __init__(self, scopes):
        self.scopes = {s.scope_id: s for s in scopes}

    async def ids(self):
        return sorted(self.scopes)

    async def all(self):
        return list(self.scopes.values())

    async def get(self, scope_id):
        if scope_id not in self.scopes:
            raise ScopeNotFoundError(scope_id)
        return self.scopes[scope_id]


class _PubSub:
    async def publish(self, topics, data=None):
        return None


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _state(monkeypatch, tmp_path):
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", 0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)
    monkeypatch.setattr(opal_server_config, "SCOPES_ORPHAN_SWEEP_MAX_SHARE", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [])
    monkeypatch.setattr(metrics, "increment", lambda *a, **k: None)
    monkeypatch.setattr(metrics, "gauge", lambda *a, **k: None)
    monkeypatch.setattr(git_fetcher, "_repacks_due", {})
    monkeypatch.setattr(git_fetcher, "_sync_passes_in_flight", 0)
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    yield
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()


def _origin(path: Path, text: str) -> str:
    repo = git.Repo.init(path, initial_branch="main")
    (path / "policy").mkdir()
    (path / "policy" / "a.rego").write_text(text)
    repo.index.add(["policy/a.rego"])
    repo.index.commit(text, author=_AUTHOR, committer=_AUTHOR)
    return path.as_uri()


def _commit(path: Path, text: str) -> None:
    repo = git.Repo(path)
    (path / "policy" / "a.rego").write_text(text)
    repo.index.add(["policy/a.rego"])
    repo.index.commit(text, author=_AUTHOR, committer=_AUTHOR)


def _scope(scope_id: str, url: str) -> Scope:
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git", url=url, branch="main", auth=NoAuthData()
        ),
    )


@pytest.mark.asyncio
async def test_syncs_beside_the_sweep_keep_the_live_clone_and_lose_the_orphan(
    tmp_path,
):
    live_url = _origin(tmp_path / "live-origin", "package live\n")
    gone_url = _origin(tmp_path / "gone-origin", "package gone\n")
    live, gone = _scope("live", live_url), _scope("gone", gone_url)
    store = _Store([live, gone])
    service = ScopesService(base_dir=tmp_path, scopes=store, pubsub_endpoint=_PubSub())
    await service.sync_scopes()
    clones = GitPolicyFetcher.base_dir(tmp_path)
    live_clone = clones / GitPolicyFetcher.source_id(live.policy)
    gone_clone = clones / GitPolicyFetcher.source_id(gone.policy)
    assert clone_landed(live_clone / ".git") and clone_landed(gone_clone / ".git")
    del store.scopes["gone"]
    clock = _Clock()
    sweeper = OrphanCloneSweeper(tmp_path, store, 60.0, clock=clock)

    async def keep_syncing():
        for i in range(6):
            _commit(tmp_path / "live-origin", f"package live\n# {i}\n")
            await service.sync_scopes()

    async def keep_sweeping():
        outcomes = []
        for _ in range(6):
            outcomes.append(await sweeper.sweep_once())
            clock.now += 60.0
            await asyncio.sleep(0)
        return outcomes

    _, outcomes = await asyncio.gather(keep_syncing(), keep_sweeping())

    assert sum(o.removed for o in outcomes) == 1
    assert not gone_clone.exists()
    assert clone_landed(live_clone / ".git")
    repo = pygit2.Repository(str(live_clone))
    head = repo.lookup_reference("refs/remotes/origin/main").peel(pygit2.Commit)
    assert head.message.strip().endswith("# 5")
    assert not set(GitPolicyFetcher.repo_locks) - {live_clone.name}


@pytest.mark.asyncio
async def test_the_delete_floor_and_the_sweep_remove_a_clone_once(tmp_path):
    clones = GitPolicyFetcher.base_dir(tmp_path)
    clones.mkdir()
    for i in range(20):
        path = clones / f"{i:064x}-0"
        (path / ".git" / "objects").mkdir(parents=True)
        (path / ".git" / "objects" / "blob").write_bytes(b"x" * 4096)

        async def floor():
            try:
                return await remove_clone_dir_exclusive(str(path))
            except FileNotFoundError:
                return None  # the sweep was first: as the floor reads it

        swept, floored = await asyncio.gather(
            asyncio.to_thread(reclaim_clone_dir_unless_busy, str(path)), floor()
        )

        assert not path.exists()
        assert True in (swept, floored)
    assert git_cli._lock_fds == {}
    assert git_fetcher._repack_lock_fds == set()


def test_ops_taking_the_lock_never_hold_it_together_while_the_sweep_unlinks_it(
    tmp_path,
):
    """Ops on two threads take and drop a clone's lock while the sweep removes
    the clone and unlinks its lock file, again and again: no two ever hold it
    at once."""
    clones = GitPolicyFetcher.base_dir(tmp_path)
    clones.mkdir()
    path = clones / ("9" * 64 + "-0")
    holders: List[int] = []
    overlaps: List[int] = []
    guard = threading.Lock()
    stop = threading.Event()

    def op():
        while not stop.is_set():
            fd = git_cli.take_clone_lock(path)
            if fd is None:
                continue
            with guard:
                holders.append(fd)
                if len(holders) > 1:
                    overlaps.append(len(holders))
            with guard:
                holders.remove(fd)
            git_cli.drop_clone_lock(fd)

    threads = [threading.Thread(target=op) for _ in range(2)]
    for thread in threads:
        thread.start()
    try:
        for _ in range(300):
            path.mkdir(exist_ok=True)
            reclaim_clone_dir_unless_busy(str(path))
    finally:
        stop.set()
        for thread in threads:
            thread.join()

    assert overlaps == []
    assert git_cli._lock_fds == {}


@pytest.mark.asyncio
async def test_the_walks_of_git_sources_run_beside_the_sweep(tmp_path, monkeypatch):
    """What reads git_sources on every worker or every heartbeat (the bundle
    route's clone-under-way check, the fetch marks, the fetch metrics,
    readiness) never fails on a clone the sweep removes under it."""
    url = "https://git.example/required.git"
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [url])
    clones = GitPolicyFetcher.base_dir(tmp_path)
    clones.mkdir()
    names = [f"{i:064x}-0" for i in range(60)]
    for name in names:
        git_dir = clones / name / ".git"
        (git_dir / "opal-fetched").mkdir(parents=True)
        (git_dir / "FETCH_HEAD").write_text("0" * 40 + "\t\tbranch 'main'\n")
        (git_dir / "opal-fetched" / "ALL").write_text("")
    errors: List[BaseException] = []
    stop = threading.Event()

    def walk():
        latch = RequiredClonesLatch()
        while not stop.is_set():
            try:
                for name in names:
                    git_cli.clone_under_way(clones / name)
                    fetch_mark_after(clones / name, "main", 0.0)
                emit_repo_fetch_metrics(tmp_path)
                latch.missing(tmp_path)
            except BaseException as e:  # noqa: BLE001 - any error fails the test
                errors.append(e)
                return

    walker = threading.Thread(target=walk)
    walker.start()
    try:
        for name in names:
            assert await asyncio.to_thread(
                reclaim_clone_dir_unless_busy, str(clones / name)
            )
    finally:
        stop.set()
        walker.join()

    assert errors == []
    assert {p.name for p in clones.iterdir()} == set()


def test_the_sweep_removes_a_clone_while_its_reflogs_are_being_removed(
    tmp_path, monkeypatch
):
    """The reflog removal thread deletes a clone's set-aside reflogs outside
    every lock; the sweep removing that clone at the same time never fails, and
    neither does the thread."""
    failed_steps: List[str] = []
    monkeypatch.setattr(git_fetcher, "_emit_ref_step_failed", failed_steps.append)
    clones = GitPolicyFetcher.base_dir(tmp_path)
    clones.mkdir()
    for i in range(5):
        path = clones / f"{i:064x}-1"
        aside = path / ".git" / f"{git_cli.REFLOGS_SET_ASIDE}x{i}"
        for d in range(40):
            leaf = aside / "refs" / "heads" / "scopes" / f"d{d}"
            leaf.mkdir(parents=True)
            for f in range(50):
                (leaf / f"s{f}").write_text("0" * 81 + "\n")
        remover = threading.Thread(target=git_fetcher._remove_reflogs, args=([aside],))
        remover.start()
        try:
            assert reclaim_clone_dir_unless_busy(str(path)) is True
        finally:
            remover.join()
        assert not path.exists()
    assert failed_steps == []
