"""SCOPES_GIT_STALE_CLONE_MAX_AGE: the pre-fork preload moves aside the clones
that stopped fetching, so its sync clones them fresh, then deletes the old copy
or, when the sync could not clone it again, moves it back."""
import fcntl
import os
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import opal_common.logger as opal_common_logger
import opal_server.git_fetcher as git_fetcher_module
import opal_server.scopes.task as task_module
import pygit2
import pytest
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    QuarantinedClone,
    quarantine_stale_scope_clones,
    settle_quarantined_clones,
    stale_clone_sweep_enabled,
)

_HOUR = 3600.0


def _source_id(n: int, shard: int = 0) -> str:
    return f"{n:064x}-{shard}"


def _make_clone(base_dir: Path, name: str, *, fetch_head_age=None, head_age=None):
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
def sweep_on(monkeypatch):
    """The sweep enabled with sane neighbours: a 60 s periodic pass and a
    150 s fetch timeout, so any max age above 210 s is accepted."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_STALE_CLONE_MAX_AGE", 900.0)
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 60)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 150.0)


@pytest.fixture
def metric_calls(monkeypatch):
    seen = []
    monkeypatch.setattr(
        git_fetcher_module.metrics,
        "increment",
        lambda name, *a, tags=None, **k: seen.append((name, tags)),
    )
    return seen


# --- when the sweep runs at all ---------------------------------------------------


def test_disabled_by_default_and_touches_nothing(tmp_path, monkeypatch):
    stale = _make_clone(tmp_path, _source_id(1), fetch_head_age=10 * _HOUR)

    def _no_disk(*a, **k):
        raise AssertionError("a disabled sweep must not touch the disk")

    monkeypatch.setattr(git_fetcher_module.os, "scandir", _no_disk)
    monkeypatch.setattr(git_fetcher_module, "_take_repack_lock", _no_disk)
    assert opal_server_config.SCOPES_GIT_STALE_CLONE_MAX_AGE == 0.0
    assert not stale_clone_sweep_enabled()
    assert quarantine_stale_scope_clones(tmp_path, {_source_id(1)}) == []
    assert stale.exists()


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_non_positive_or_non_finite_values_disable_it(
    tmp_path, sweep_on, monkeypatch, value
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_STALE_CLONE_MAX_AGE", value)
    stale = _make_clone(tmp_path, _source_id(1), fetch_head_age=10 * _HOUR)
    assert quarantine_stale_scope_clones(tmp_path, {_source_id(1)}) == []
    assert stale.exists()


def test_skipped_without_a_periodic_pass(tmp_path, sweep_on, monkeypatch):
    """With POLICY_REFRESH_INTERVAL=0 nothing is fetched regularly, so every
    healthy clone would look stale."""
    monkeypatch.setattr(opal_server_config, "POLICY_REFRESH_INTERVAL", 0)
    stale = _make_clone(tmp_path, _source_id(1), fetch_head_age=10 * _HOUR)
    assert quarantine_stale_scope_clones(tmp_path, {_source_id(1)}) == []
    assert stale.exists()


def test_skipped_when_the_age_is_too_small_to_mean_anything(
    tmp_path, sweep_on, monkeypatch
):
    """Not above one periodic pass plus a slow fetch: a clone fetching
    normally could be judged stale."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_STALE_CLONE_MAX_AGE", 200.0)
    stale = _make_clone(tmp_path, _source_id(1), fetch_head_age=10 * _HOUR)
    assert quarantine_stale_scope_clones(tmp_path, {_source_id(1)}) == []
    assert stale.exists()


def test_nothing_polled_nothing_judged(tmp_path, sweep_on):
    stale = _make_clone(tmp_path, _source_id(1), fetch_head_age=10 * _HOUR)
    assert quarantine_stale_scope_clones(tmp_path, set()) == []
    assert stale.exists()


def test_missing_git_sources_dir_is_a_new_pod(tmp_path, sweep_on):
    assert quarantine_stale_scope_clones(tmp_path / "nowhere", {_source_id(1)}) == []


def test_skipped_while_a_repack_holds_the_lock(tmp_path, sweep_on):
    """The repack lock is an flock on git_sources itself; while another open
    file description holds it, the sweep moves nothing."""
    stale = _make_clone(tmp_path, _source_id(1), fetch_head_age=10 * _HOUR)
    root = GitPolicyFetcher.base_dir(tmp_path)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert quarantine_stale_scope_clones(tmp_path, {_source_id(1)}) == []
        assert stale.exists()
    finally:
        os.close(fd)


# --- what the sweep moves -----------------------------------------------------------


def test_moves_only_stale_clones_of_polled_sources(tmp_path, sweep_on):
    stale = _make_clone(tmp_path, _source_id(1, 0), fetch_head_age=2 * _HOUR)
    fresh = _make_clone(tmp_path, _source_id(1, 1), fetch_head_age=60)
    unpolled = _make_clone(tmp_path, _source_id(2), fetch_head_age=2 * _HOUR)
    orphan = _make_clone(tmp_path, _source_id(3), fetch_head_age=50 * _HOUR)
    moved = quarantine_stale_scope_clones(
        tmp_path, {_source_id(1, 0), _source_id(1, 1)}
    )
    assert [q.source_id for q in moved] == [_source_id(1, 0)]
    q = moved[0]
    assert q.clone == stale and not stale.exists() and q.trash.is_dir()
    assert q.trash.name == f".stale-{_source_id(1, 0)}"
    assert fresh.exists() and unpolled.exists() and orphan.exists()


def test_fetch_head_wins_over_an_old_head(tmp_path, sweep_on):
    """HEAD keeps its clone-time mtime forever; a clone that fetches normally
    has a fresh FETCH_HEAD and is kept."""
    clone = _make_clone(
        tmp_path, _source_id(1), fetch_head_age=60, head_age=30 * 24 * _HOUR
    )
    assert quarantine_stale_scope_clones(tmp_path, {_source_id(1)}) == []
    assert clone.exists()


def test_a_clone_without_fetch_head_is_judged_by_head(tmp_path, sweep_on):
    old = _make_clone(tmp_path, _source_id(1, 0), head_age=2 * _HOUR)
    new = _make_clone(tmp_path, _source_id(1, 1), head_age=60)
    moved = quarantine_stale_scope_clones(
        tmp_path, {_source_id(1, 0), _source_id(1, 1)}
    )
    assert [q.source_id for q in moved] == [_source_id(1, 0)]
    assert not old.exists() and new.exists()


def test_leaves_what_it_cannot_judge(tmp_path, sweep_on):
    """No .git/FETCH_HEAD and no .git/HEAD: not a clone this sweep judges."""
    odd = GitPolicyFetcher.base_dir(tmp_path) / _source_id(1)
    (odd / ".git").mkdir(parents=True)
    assert quarantine_stale_scope_clones(tmp_path, {_source_id(1)}) == []
    assert odd.exists()


def test_touches_only_real_directories_named_like_a_source_id(tmp_path, sweep_on):
    root = GitPolicyFetcher.base_dir(tmp_path)
    newline_name = _source_id(1) + "\n"
    odd = _make_clone(tmp_path, newline_name, fetch_head_age=10 * _HOUR)
    target = _make_clone(tmp_path, "symlink-target", fetch_head_age=10 * _HOUR)
    link = root / _source_id(2)
    link.symlink_to(target, target_is_directory=True)
    a_file = root / _source_id(3)
    a_file.write_text("")
    polled = {newline_name, _source_id(2), _source_id(3)}
    assert quarantine_stale_scope_clones(tmp_path, polled) == []
    for p in (odd, target, link, a_file):
        assert p.exists(), p


def test_removes_leftovers_of_a_start_that_died_before_settling(tmp_path, sweep_on):
    root = GitPolicyFetcher.base_dir(tmp_path)
    fresh = _make_clone(tmp_path, _source_id(1), fetch_head_age=30)
    leftover = root / f".stale-{_source_id(1)}"
    (leftover / ".git").mkdir(parents=True)
    assert quarantine_stale_scope_clones(tmp_path, {_source_id(1)}) == []
    assert not leftover.exists() and fresh.exists()


def test_a_failed_move_keeps_the_clone(tmp_path, sweep_on, monkeypatch):
    stuck = _make_clone(tmp_path, _source_id(1, 0), fetch_head_age=10 * _HOUR)
    other = _make_clone(tmp_path, _source_id(1, 1), fetch_head_age=10 * _HOUR)
    real_rename = os.rename

    def _rename(src, dst):
        if Path(src) == stuck:
            raise PermissionError(13, "Permission denied", str(src))
        return real_rename(src, dst)

    monkeypatch.setattr(git_fetcher_module.os, "rename", _rename)
    moved = quarantine_stale_scope_clones(
        tmp_path, {_source_id(1, 0), _source_id(1, 1)}
    )
    assert [q.source_id for q in moved] == [_source_id(1, 1)]
    assert stuck.exists() and not other.exists()


def test_an_unlistable_root_is_logged_not_raised(tmp_path, sweep_on, monkeypatch):
    _make_clone(tmp_path, _source_id(1), fetch_head_age=10 * _HOUR)

    def _denied(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(git_fetcher_module.os, "scandir", _denied)
    assert quarantine_stale_scope_clones(tmp_path, {_source_id(1)}) == []


# --- settling after the sync --------------------------------------------------------


def _moved_one(tmp_path) -> QuarantinedClone:
    _make_clone(tmp_path, _source_id(1), fetch_head_age=10 * _HOUR)
    (q,) = quarantine_stale_scope_clones(tmp_path, {_source_id(1)})
    return q


def test_settle_deletes_the_old_copy_once_cloned_again(
    tmp_path, sweep_on, metric_calls
):
    q = _moved_one(tmp_path)
    _make_clone(tmp_path, q.source_id, fetch_head_age=0)  # the sync's new clone
    settle_quarantined_clones([q])
    assert q.clone.exists() and not q.trash.exists()
    assert metric_calls == [("opal_server.scopes.stale_clone", {"outcome": "recloned"})]


def test_settle_restores_the_old_copy_when_the_clone_failed(
    tmp_path, sweep_on, metric_calls
):
    """The remote is unreachable, say: the last fetched policy beats none."""
    q = _moved_one(tmp_path)
    settle_quarantined_clones([q])
    assert not q.trash.exists()
    assert (q.clone / ".git" / "FETCH_HEAD").exists()  # the old copy, back
    assert metric_calls == [("opal_server.scopes.stale_clone", {"outcome": "restored"})]


def test_settle_replaces_a_partial_failed_clone_with_the_old_copy(
    tmp_path, sweep_on, metric_calls
):
    q = _moved_one(tmp_path)
    (q.clone / "half-written").mkdir(parents=True)  # no FETCH_HEAD, no HEAD
    settle_quarantined_clones([q])
    assert not (q.clone / "half-written").exists()
    assert (q.clone / ".git" / "FETCH_HEAD").exists()
    assert metric_calls[-1][1] == {"outcome": "restored"}


def test_settle_leaves_a_clone_still_in_flight_alone(
    tmp_path, sweep_on, metric_calls, monkeypatch
):
    q = _moved_one(tmp_path)
    (q.clone / "being-cloned").mkdir(parents=True)
    monkeypatch.setattr(
        git_fetcher_module, "git_op_in_flight", lambda key: key == q.source_id
    )
    settle_quarantined_clones([q])
    assert (q.clone / "being-cloned").exists()  # the live clone, untouched
    assert q.trash.exists()  # deleted by the next start's sweep
    assert metric_calls[-1][1] == {"outcome": "in_flight"}


def test_settle_never_raises(tmp_path, sweep_on, metric_calls, monkeypatch):
    q = _moved_one(tmp_path)

    def _boom(*a, **k):
        raise OSError("disk gone")

    monkeypatch.setattr(git_fetcher_module.os, "rename", _boom)
    settle_quarantined_clones([q])
    assert metric_calls[-1][1] == {"outcome": "lost"}


# --- the preload wiring ---------------------------------------------------------------


def _scope(url: str, branch: str = "main", poll: bool = True):
    return SimpleNamespace(
        policy=SimpleNamespace(url=url, branch=branch, poll_updates=poll)
    )


@pytest.fixture
def preload(monkeypatch, tmp_path):
    """preload_scopes() against tmp_path, with Redis and the sync stubbed.

    Set ``state['scopes']`` and ``state['sync']`` before calling run().
    """
    state = {"scopes": [], "sync": None, "events": []}
    monkeypatch.setattr(opal_common_logger, "_logs_configured", True)
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)
    monkeypatch.setattr(task_module, "RedisDB", lambda url: object())

    class _Scopes:
        def __init__(self, db):
            pass

        async def all(self):
            state["events"].append("scopes.all")
            return state["scopes"]

    class _Service:
        def __init__(self, *args, **kwargs):
            pass

        async def sync_scopes(self, *args, **kwargs):
            state["events"].append("sync_scopes")
            if state["sync"]:
                state["sync"]()

    real_settle = task_module.settle_quarantined_clones

    def _settle(moved):
        state["events"].append("settle")
        real_settle(moved)

    monkeypatch.setattr(task_module, "ScopeRepository", _Scopes)
    monkeypatch.setattr(task_module, "ScopesService", _Service)
    monkeypatch.setattr(task_module, "settle_quarantined_clones", _settle)
    monkeypatch.setattr(task_module, "drain_git_ops", lambda timeout: True)
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    state["run"] = task_module.ScopesPolicyWatcherTask.preload_scopes
    return state


def test_preload_disabled_never_reads_scopes_for_the_sweep(preload):
    preload["run"]()
    assert preload["events"] == ["sync_scopes", "settle"]


def test_preload_recloned_and_restored_end_to_end(tmp_path, sweep_on, preload):
    """Two stale polled sources: the sync clones one again and fails the other.
    The first old copy is deleted, the second is put back; an unpolled stale
    clone and a fresh one are left alone."""
    ok, down, idle, fresh = (
        _scope("https://git.example/ok.git"),
        _scope("https://git.example/down.git"),
        _scope("https://git.example/idle.git", poll=False),
        _scope("https://git.example/fresh.git"),
    )
    ids = {
        k: GitPolicyFetcher.source_id(s.policy)
        for k, s in (("ok", ok), ("down", down), ("idle", idle), ("fresh", fresh))
    }
    for k in ("ok", "down", "idle"):
        _make_clone(tmp_path, ids[k], fetch_head_age=2 * _HOUR)
    _make_clone(tmp_path, ids["fresh"], fetch_head_age=30)
    preload["scopes"] = [ok, down, idle, fresh]
    root = GitPolicyFetcher.base_dir(tmp_path)
    at_sync = {}

    def _sync():
        at_sync.update({k: (root / v).exists() for k, v in ids.items()})
        _make_clone(tmp_path, ids["ok"], fetch_head_age=0)  # cloned again

    preload["sync"] = _sync
    preload["run"]()
    assert preload["events"] == ["scopes.all", "sync_scopes", "settle"]
    assert at_sync == {"ok": False, "down": False, "idle": True, "fresh": True}
    for k in ids:
        assert (root / ids[k]).is_dir(), k
    assert not any(p.name.startswith(".stale-") for p in root.iterdir())
    fetched = (root / ids["down"] / ".git" / "FETCH_HEAD").stat().st_mtime
    assert time.time() - fetched > _HOUR  # the old copy, put back


def test_preload_settles_even_when_the_sync_raises(tmp_path, sweep_on, preload):
    s = _scope("https://git.example/a.git")
    sid = GitPolicyFetcher.source_id(s.policy)
    _make_clone(tmp_path, sid, fetch_head_age=2 * _HOUR)
    preload["scopes"] = [s]

    def _sync():
        raise RuntimeError("redis went away")

    preload["sync"] = _sync
    with pytest.raises(RuntimeError):
        preload["run"]()
    assert preload["events"][-1] == "settle"
    assert (GitPolicyFetcher.base_dir(tmp_path) / sid / ".git" / "FETCH_HEAD").exists()


def test_preload_sweep_failure_does_not_block_the_sync(sweep_on, preload, monkeypatch):
    def _boom(base_dir, polled):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(task_module, "quarantine_stale_scope_clones", _boom)
    preload["scopes"] = [_scope("https://git.example/a.git")]
    preload["run"]()
    assert preload["events"] == ["scopes.all", "sync_scopes", "settle"]


def test_no_preload_no_sweep_when_scopes_are_off(preload, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    preload["run"]()
    assert preload["events"] == []


# --- the libgit2 behaviour the sweep's age relies on -----------------------------------


def test_libgit2_rewrites_fetch_head_on_every_fetch(tmp_path):
    """The age is only right if the clone itself writes FETCH_HEAD and every
    fetch, an up-to-date one included, rewrites it."""
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
    fetch_head = clone / ".git" / "FETCH_HEAD"
    assert fetch_head.exists()  # written by the clone's own fetch
    os.utime(fetch_head, (1, 1))  # pretend it is ancient
    repo.remotes["origin"].fetch()  # nothing new on the remote
    assert fetch_head.stat().st_mtime > 1
    repo.free()
