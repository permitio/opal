"""remove_stale_scope_clones(): the pre-fork preload deletes the scope clones
that stopped fetching, so a restarted container clones them fresh instead of
reusing them (SCOPES_GIT_STALE_CLONE_MAX_AGE)."""
import os
import shutil
import time
from pathlib import Path

import opal_common.logger as opal_common_logger
import opal_server.git_fetcher as git_fetcher_module
import opal_server.scopes.task as task_module
import pytest
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, remove_stale_scope_clones

_HOUR = 3600.0


def _source_id(n: int, shard: int = 0) -> str:
    return f"{n:064x}-{shard}"


def _make_clone(
    base_dir: Path,
    name: str,
    *,
    fetch_head_age=None,
    head_age=None,
) -> Path:
    """A directory that looks like a scope clone, with the ages given (seconds
    in the past) as mtimes.

    None leaves that file out.
    """
    git_dir = GitPolicyFetcher.base_dir(base_dir) / name / ".git"
    git_dir.mkdir(parents=True)
    now = time.time()
    for fname, age in (("FETCH_HEAD", fetch_head_age), ("HEAD", head_age)):
        if age is None:
            continue
        f = git_dir / fname
        f.write_text("x")
        os.utime(f, (now - age, now - age))
    return git_dir.parent


@pytest.fixture
def max_age(monkeypatch):
    def _set(value):
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_STALE_CLONE_MAX_AGE", value)

    return _set


def test_disabled_by_default_and_touches_nothing(tmp_path, monkeypatch):
    stale = _make_clone(tmp_path, _source_id(1), fetch_head_age=10 * _HOUR)

    def _no_disk(*a, **k):
        raise AssertionError("a disabled sweep must not touch the disk")

    monkeypatch.setattr(git_fetcher_module.os, "scandir", _no_disk)
    assert opal_server_config.SCOPES_GIT_STALE_CLONE_MAX_AGE == 0.0
    assert remove_stale_scope_clones(tmp_path) == 0
    assert stale.exists()


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_non_positive_or_non_finite_values_disable_it(tmp_path, max_age, value):
    max_age(value)
    stale = _make_clone(tmp_path, _source_id(1), fetch_head_age=10 * _HOUR)
    assert remove_stale_scope_clones(tmp_path) == 0
    assert stale.exists()


def test_deletes_only_the_clones_past_the_age(tmp_path, max_age):
    max_age(900)
    stale = _make_clone(tmp_path, _source_id(1, 0), fetch_head_age=2 * _HOUR)
    fresh = _make_clone(tmp_path, _source_id(1, 1), fetch_head_age=60)
    assert remove_stale_scope_clones(tmp_path) == 1
    assert not stale.exists()
    assert fresh.exists()


def test_fetch_head_wins_over_an_old_head(tmp_path, max_age):
    """HEAD keeps its clone-time mtime forever; a clone that fetches normally
    has a fresh FETCH_HEAD and must be kept."""
    max_age(900)
    clone = _make_clone(
        tmp_path, _source_id(2), fetch_head_age=60, head_age=30 * 24 * _HOUR
    )
    assert remove_stale_scope_clones(tmp_path) == 0
    assert clone.exists()


def test_a_clone_without_fetch_head_is_judged_by_head(tmp_path, max_age):
    max_age(900)
    old = _make_clone(tmp_path, _source_id(3, 0), head_age=2 * _HOUR)
    new = _make_clone(tmp_path, _source_id(3, 1), head_age=60)
    assert remove_stale_scope_clones(tmp_path) == 1
    assert not old.exists()
    assert new.exists()


def test_leaves_what_it_cannot_judge(tmp_path, max_age):
    """No .git/FETCH_HEAD and no .git/HEAD: not a clone this sweep judges
    (_get_valid_repo handles an unusable one)."""
    max_age(900)
    odd = GitPolicyFetcher.base_dir(tmp_path) / _source_id(4)
    (odd / ".git").mkdir(parents=True)
    assert remove_stale_scope_clones(tmp_path) == 0
    assert odd.exists()


def test_touches_only_directories_named_like_a_source_id(tmp_path, max_age):
    max_age(900)
    root = GitPolicyFetcher.base_dir(tmp_path)
    other = _make_clone(tmp_path, "not-a-source-id", fetch_head_age=10 * _HOUR)
    short = _make_clone(tmp_path, "abc-0", fetch_head_age=10 * _HOUR)
    lock_file = root / "repack.lock"
    lock_file.write_text("")
    target = _make_clone(tmp_path, "symlink-target", fetch_head_age=10 * _HOUR)
    link = root / _source_id(5)
    link.symlink_to(target, target_is_directory=True)
    assert remove_stale_scope_clones(tmp_path) == 0
    for p in (other, short, lock_file, target, link):
        assert p.exists(), p


def test_missing_git_sources_dir_is_a_new_pod(tmp_path, max_age):
    max_age(900)
    assert remove_stale_scope_clones(tmp_path / "nothing-here") == 0


def test_an_unlistable_root_is_logged_not_raised(tmp_path, max_age, monkeypatch):
    max_age(900)
    _make_clone(tmp_path, _source_id(6), fetch_head_age=10 * _HOUR)

    def _denied(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(git_fetcher_module.os, "scandir", _denied)
    assert remove_stale_scope_clones(tmp_path) == 0


def test_a_failed_delete_keeps_the_clone_and_continues(tmp_path, max_age, monkeypatch):
    max_age(900)
    stuck = _make_clone(tmp_path, _source_id(7, 0), fetch_head_age=10 * _HOUR)
    other = _make_clone(tmp_path, _source_id(7, 1), fetch_head_age=10 * _HOUR)
    real_rmtree = shutil.rmtree

    def _rmtree(path, *a, **k):
        if Path(path) == stuck:
            raise PermissionError(13, "Permission denied", str(path))
        return real_rmtree(path, *a, **k)

    monkeypatch.setattr(git_fetcher_module.shutil, "rmtree", _rmtree)
    assert remove_stale_scope_clones(tmp_path) == 1
    assert stuck.exists()
    assert not other.exists()


def test_counts_each_deleted_clone_in_the_metric(tmp_path, max_age, monkeypatch):
    max_age(900)
    for shard in range(3):
        _make_clone(tmp_path, _source_id(8, shard), fetch_head_age=10 * _HOUR)
    seen = []
    monkeypatch.setattr(
        git_fetcher_module.metrics,
        "increment",
        lambda name, *a, **k: seen.append(name),
    )
    assert remove_stale_scope_clones(tmp_path) == 3
    assert seen == ["opal_server.scopes.stale_clone_removed"] * 3


# --- the preload wiring ---------------------------------------------------------


@pytest.fixture
def _preload_stubs(monkeypatch):
    """preload_scopes() with its sync and teardown stubbed, recording order."""
    events = []
    monkeypatch.setattr(opal_common_logger, "_logs_configured", True)
    monkeypatch.setattr(task_module, "RedisDB", lambda url: object())
    monkeypatch.setattr(task_module, "ScopeRepository", lambda db: object())
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)

    class _StubService:
        def __init__(self, *args, **kwargs):
            pass

        async def sync_scopes(self, *args, **kwargs):
            events.append("sync_scopes")

    monkeypatch.setattr(task_module, "ScopesService", _StubService)
    monkeypatch.setattr(task_module, "drain_git_ops", lambda timeout: True)
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    yield events


def test_preload_sweeps_before_it_syncs(monkeypatch, _preload_stubs, tmp_path):
    events = _preload_stubs
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    seen_base = []

    def _sweep(base_dir):
        seen_base.append(base_dir)
        events.append("sweep")
        return 0

    monkeypatch.setattr(task_module, "remove_stale_scope_clones", _sweep)
    task_module.ScopesPolicyWatcherTask.preload_scopes()
    assert events[:2] == ["sweep", "sync_scopes"]
    assert seen_base == [Path(str(tmp_path))]


def test_preload_deletes_a_stale_clone_end_to_end(
    monkeypatch, _preload_stubs, tmp_path, max_age
):
    """Real sweep inside the real preload: the stale clone is gone by the time
    the (stubbed) sync starts, the fresh one is still there."""
    max_age(900)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    stale = _make_clone(tmp_path, _source_id(9, 0), fetch_head_age=2 * _HOUR)
    fresh = _make_clone(tmp_path, _source_id(9, 1), fetch_head_age=30)
    at_sync = {}

    class _Probe:
        def __init__(self, *args, **kwargs):
            pass

        async def sync_scopes(self, *args, **kwargs):
            at_sync["stale"] = stale.exists()
            at_sync["fresh"] = fresh.exists()

    monkeypatch.setattr(task_module, "ScopesService", _Probe)
    task_module.ScopesPolicyWatcherTask.preload_scopes()
    assert at_sync == {"stale": False, "fresh": True}


def test_no_preload_no_sweep_when_scopes_are_off(monkeypatch, _preload_stubs):
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    called = []
    monkeypatch.setattr(
        task_module, "remove_stale_scope_clones", lambda b: called.append(b)
    )
    task_module.ScopesPolicyWatcherTask.preload_scopes()
    assert called == []


# --- the libgit2 behaviour the sweep's age relies on -----------------------------


def test_libgit2_rewrites_fetch_head_on_every_fetch(tmp_path):
    """The age is only right if the clone itself writes FETCH_HEAD and every
    fetch, an up-to-date one included, rewrites it."""
    import subprocess

    import pygit2

    origin = tmp_path / "origin"
    subprocess.run(["git", "init", "-q", str(origin)], check=True)
    for args in (
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "t"],
        ["commit", "-q", "--allow-empty", "-m", "c1"],
    ):
        subprocess.run(["git", "-C", str(origin), *args], check=True)

    clone = tmp_path / "clone"
    repo = pygit2.clone_repository(str(origin), str(clone))
    git_dir = clone / ".git"
    fetch_head = git_dir / "FETCH_HEAD"
    assert fetch_head.exists()  # written by the clone's own fetch
    os.utime(fetch_head, (1, 1))  # pretend it is ancient
    repo.remotes["origin"].fetch()  # nothing new on the remote
    assert fetch_head.stat().st_mtime > 1
    repo.free()
