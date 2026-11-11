"""A sync pass fetches a clone once for every branch its remote lacks, and one
clone's slow sync holds one phase-2 slot (PER-17994).

A scope whose branch is not in its clone makes its sync fetch the clone. A
pass (the periodic one, a refresh of every scope, the boot preload) kept no
record of that fetch, so each scope of a clone whose remote lacks its branch
fetched the clone again: N such scopes cost N fetches in every pass, and one
"Did not find target branch" ERROR each. Phase 1 of a pass already fetches
every clone, so a scope whose branch is missing no longer fetches its clone
again once the clone was fetched after the pass started, and the ERROR is
logged once per branch per pass.

Phase 2 ran each scope as its own task under the SCOPES_GIT_MAX_WORKERS
semaphore, and a task takes its slot before it waits for its clone's lock. A
clone whose sync was slow then filled every slot with its own scopes, all
waiting for that lock, and no scope of any other clone ran. Phase 2 now gives
each clone one slot, in which a few of its scopes run at once, and runs the
clones side by side, so a slow clone holds one slot.

The tests use real clones of local origins, with libgit2 and with the git
command line (SCOPES_GIT_FETCH_WITH_CLI). Fetches and clones are counted on
pygit2's own calls, or git_cli's, which still run.
"""

import asyncio
import collections
import contextlib
import contextvars
import datetime
from pathlib import Path

import git
import opal_server.scopes.task as task_module
import pygit2
import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_common.tests.log_capture import capture_records
from opal_server import git_fetcher
from opal_server.config import opal_server_config
from opal_server.git_cli import GitCliError
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import _SCOPES_IN_FLIGHT_PER_CLONE, ScopesService
from opal_server.scopes.task import ScopesPolicyWatcherTask

_AUTHOR = git.Actor("test", "test@example.com")
_MISSING = "Did not find target branch on remote: "
_WAIT = 10

# The number of the phase-2 slot the current task's scopes run under (see
# _NumberedSlots).
_slot: contextvars.ContextVar = contextvars.ContextVar("_slot", default=None)


class _Scopes:
    """``deleted``: scopes the pass's listing has, but that are gone by the
    time their sync reads them.

    ``moved``: scopes that read back as these
    (repointed) versions.
    """

    def __init__(self, scopes, deleted=(), moved=None):
        self._scopes = {s.scope_id: s for s in scopes}
        self._deleted = set(deleted)
        self._moved = dict(moved or {})

    async def get(self, scope_id):
        if scope_id not in self._scopes or scope_id in self._deleted:
            raise ScopeNotFoundError(scope_id)
        return self._moved.get(scope_id, self._scopes[scope_id])

    async def all(self):
        return list(self._scopes.values())


class _PubSub:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append((list(topics), data))

    def notified_scopes(self):
        return {
            topic.split(":", 1)[0] for topics, _ in self.published for topic in topics
        }


class _GitOps:
    """The URLs fetched and cloned, by pygit2 or git_cli, in order.

    ``fail``: how the next fetches fail, one each: a message, for the
    remote's error, or the exception to raise.
    """

    def __init__(self):
        self.fetches = []
        self.clones = []
        self.fail = []


class _NumberedSlots:
    """Wraps phase 2's semaphore and numbers each slot taken.

    The task that takes a slot, and every task it starts, sees the
    slot's number in _slot.
    """

    def __init__(self, semaphore):
        self._semaphore = semaphore
        self._taken = 0

    async def acquire(self):
        await self._semaphore.acquire()
        self._taken += 1
        _slot.set(self._taken)

    def release(self):
        self._semaphore.release()

    async def __aenter__(self):
        await self.acquire()

    async def __aexit__(self, *exc_info):
        self.release()


@pytest.fixture(autouse=True, params=["libgit2", "cli"])
def _backend(request, monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", request.param == "cli"
    )


@pytest.fixture(autouse=True)
def _clean_fetcher_state(monkeypatch):
    # One clone per URL whatever the environment says, and no repack at the
    # end of a pass: neither is what these tests are about.
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", 0)
    monkeypatch.setattr(git_fetcher, "_repacks_due", {})
    monkeypatch.setattr(git_fetcher, "_sync_passes_in_flight", 0)
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    yield
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()


@pytest.fixture
def git_ops(monkeypatch):
    ops = _GitOps()
    real_fetch = pygit2.remotes.Remote.fetch
    real_clone = git_fetcher.clone_repository
    real_cli_fetch = git_fetcher.cli_fetch
    real_cli_clone = git_fetcher.cli_clone

    def fetch(remote, *args, **kwargs):
        ops.fetches.append(remote.url)
        if ops.fail:
            failure = ops.fail.pop()
            raise pygit2.GitError(failure) if isinstance(failure, str) else failure
        return real_fetch(remote, *args, **kwargs)

    def clone(url, *args, **kwargs):
        ops.clones.append(url)
        return real_clone(url, *args, **kwargs)

    async def cli_fetch(repo_path, remote, source, **kwargs):
        ops.fetches.append(source.url)
        if ops.fail:
            kwargs["on_gone"](False)
            failure = ops.fail.pop()
            if isinstance(failure, str):
                raise GitCliError(128, f"fatal: {failure}")
            raise failure
        return await real_cli_fetch(repo_path, remote, source, **kwargs)

    async def cli_clone(url, *args, **kwargs):
        ops.clones.append(url)
        return await real_cli_clone(url, *args, **kwargs)

    monkeypatch.setattr(pygit2.remotes.Remote, "fetch", fetch)
    monkeypatch.setattr(git_fetcher, "clone_repository", clone)
    monkeypatch.setattr(git_fetcher, "cli_fetch", cli_fetch)
    monkeypatch.setattr(git_fetcher, "cli_clone", cli_clone)
    return ops


def _commit(repo: git.Repo, relpath: str, contents: str) -> None:
    path = Path(repo.working_tree_dir) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    repo.index.add([relpath])
    repo.index.commit(f"update {relpath}", author=_AUTHOR, committer=_AUTHOR)


def _origin(path: Path) -> git.Repo:
    repo = git.Repo.init(path, initial_branch="main")
    _commit(repo, "policy/a.rego", "package a\n")
    return repo


def _scope(scope_id: str, origin: git.Repo, branch: str = "main") -> Scope:
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git",
            url=origin.working_tree_dir,
            branch=branch,
            auth=NoAuthData(),
        ),
    )


def _service(tmp_path: Path, scopes, pubsub=None) -> ScopesService:
    return ScopesService(
        base_dir=tmp_path / "opal",
        scopes=_Scopes(scopes),
        pubsub_endpoint=pubsub if pubsub is not None else _PubSub(),
    )


def _missing_branch_errors(records):
    """The missing-branch ERRORs logged, counted by branch (each line ends in
    the source's URL, in parentheses)."""
    return collections.Counter(
        r["message"][len(_MISSING) :].split(" (", 1)[0]
        for r in records
        if r["level"].name == "ERROR" and r["message"].startswith(_MISSING)
    )


def _scopes_on_missing_branches(origin: git.Repo):
    """One scope on main, then five whose branches the origin lacks."""
    return [_scope("s-main", origin)] + [
        _scope(f"s{i}", origin, f"gone-{i}") for i in range(1, 6)
    ]


# --- one fetch per clone per pass --------------------------------------------


@pytest.mark.asyncio
async def test_a_pass_fetches_a_clone_once_for_all_its_missing_branches(
    tmp_path, git_ops
):
    """Mutation: dropping the pass-start check from _should_fetch makes each of
    the five scopes on a missing branch fetch again (six fetches)."""
    origin = _origin(tmp_path / "origin")
    svc = _service(tmp_path, _scopes_on_missing_branches(origin))
    await svc.sync_scope(scope_id="s-main")
    assert git_ops.clones == [origin.working_tree_dir]

    await svc.sync_scopes()

    assert git_ops.fetches == [origin.working_tree_dir]


@pytest.mark.asyncio
async def test_a_clone_phase_1_did_not_fetch_is_fetched_once_in_phase_2(
    tmp_path, git_ops
):
    """Phase 1 fetches nothing for a clone whose scope was deleted after the
    pass listed it; the first phase-2 scope on a missing branch fetches the
    clone, and the others ride that fetch."""
    origin = _origin(tmp_path / "origin")
    scopes = _scopes_on_missing_branches(origin)
    await _service(tmp_path, scopes).sync_scope(scope_id="s-main")
    svc = ScopesService(
        base_dir=tmp_path / "opal",
        scopes=_Scopes(scopes, deleted={"s-main"}),
        pubsub_endpoint=_PubSub(),
    )

    await svc.sync_scopes()

    assert git_ops.fetches == [origin.working_tree_dir]


@pytest.mark.asyncio
async def test_the_next_pass_fetches_a_missing_branch_again_when_phase_1_did_not(
    tmp_path, git_ops
):
    """The rule lasts one pass. Phase 1 fetches nothing here (its scope is
    gone), so only the pass rule decides: the next pass fetches again and finds
    the branch pushed in between.

    Mutation: a pass start that stays the same across passes keeps the
    branch missing.
    """
    origin = _origin(tmp_path / "origin")
    scopes = _scopes_on_missing_branches(origin)
    await _service(tmp_path, scopes).sync_scope(scope_id="s-main")
    pubsub = _PubSub()
    svc = ScopesService(
        base_dir=tmp_path / "opal",
        scopes=_Scopes(scopes, deleted={"s-main"}),
        pubsub_endpoint=pubsub,
    )
    await svc.sync_scopes()
    assert len(git_ops.fetches) == 1

    origin.create_head("gone-3")
    await svc.sync_scopes()

    assert len(git_ops.fetches) == 2
    assert "s3" in pubsub.notified_scopes()


@pytest.mark.asyncio
async def test_a_branch_pushed_between_passes_is_served_by_the_next_pass(
    tmp_path, git_ops
):
    """Phase 1's forced fetch of the next pass brings the branch, and the scope
    on it is notified; nothing from the pass before keeps it missing."""
    origin = _origin(tmp_path / "origin")
    pubsub = _PubSub()
    svc = _service(tmp_path, _scopes_on_missing_branches(origin), pubsub)
    await svc.sync_scope(scope_id="s-main")
    await svc.sync_scopes()
    assert len(git_ops.fetches) == 1
    assert "s3" not in pubsub.notified_scopes()

    origin.create_head("gone-3")
    await svc.sync_scopes()

    assert len(git_ops.fetches) == 2
    assert "s3" in pubsub.notified_scopes()


@pytest.mark.asyncio
async def test_a_failed_phase_1_fetch_is_tried_again_by_the_next_pass_not_by_phase_2(
    tmp_path, git_ops
):
    """A pass tries each clone once, whatever its op ends in: a fetch that
    failed in phase 1 is not tried again by the clone's phase-2 scopes (each
    would fail, and log it, once more), and the next pass tries it again."""
    origin = _origin(tmp_path / "origin")
    scopes = [_scope("s-main", origin), _scope("s-new", origin, "new")]
    pubsub = _PubSub()
    svc = _service(tmp_path, scopes, pubsub)
    await svc.sync_scope(scope_id="s-main")
    origin.create_head("new")
    git_ops.fail.append("remote hung up")

    # The refresh-all pass: no backoff, so only the pass keeps the source
    # from being tried again.
    await svc.sync_scopes(honor_backoff=False)

    assert len(git_ops.fetches) == 1
    assert "s-new" not in pubsub.notified_scopes()

    await svc.sync_scopes(honor_backoff=False)

    assert len(git_ops.fetches) == 2
    assert "s-new" in pubsub.notified_scopes()


def test_the_preload_clones_once_and_fetches_nothing_for_missing_branches(
    tmp_path, git_ops, monkeypatch, no_redis
):
    """The boot preload is a pass too: phase 1 clones the repository, and the
    scopes whose branches it lacks fetch nothing more."""
    origin = _origin(tmp_path / "origin")
    scopes = _Scopes(_scopes_on_missing_branches(origin))
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path / "opal"))
    monkeypatch.setattr(task_module, "ScopeRepository", lambda db: scopes)
    # Both would replace this test's log sinks and metrics client.
    monkeypatch.setattr(task_module, "configure_logs", lambda: None)
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)

    ScopesPolicyWatcherTask.preload_scopes()

    assert git_ops.clones == [origin.working_tree_dir]
    assert git_ops.fetches == []


@pytest.mark.asyncio
async def test_a_requested_sync_during_a_pass_fetches_a_branch_pushed_after_the_pass_fetched(
    tmp_path, git_ops, monkeypatch
):
    """The rule belongs to the pass's own syncs. A sync a bundle request asks
    for while a pass runs keeps the request's rule (#988): it fetches unless a
    fetch started after the request.

    Mutation: keeping the pass start in a process-wide variable instead of the
    pass's context makes this sync skip its fetch, and the branch pushed after
    the pass fetched is not served.
    """
    origin = _origin(tmp_path / "origin")
    scopes = [
        _scope("s-main", origin),
        _scope("s-hold", origin, "gone"),
        _scope("s-new", origin, "new"),
    ]
    store = _Scopes(scopes)
    svc = ScopesService(
        base_dir=tmp_path / "opal", scopes=store, pubsub_endpoint=_PubSub()
    )
    await svc.sync_scope(scope_id="s-main")
    git_ops.fetches.clear()

    paused, resume = asyncio.Event(), asyncio.Event()
    real_sync_scope = svc.sync_scope

    async def sync_scope(**kwargs):
        if kwargs["scope_id"] == "s-hold":
            paused.set()
            await resume.wait()
        return await real_sync_scope(**kwargs)

    monkeypatch.setattr(svc, "sync_scope", sync_scope)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path / "opal"))
    monkeypatch.setattr(task_module, "RedisDB", lambda url: None)
    monkeypatch.setattr(task_module, "ScopeRepository", lambda db: store)
    watcher = ScopesPolicyWatcherTask(_PubSub())

    sync_pass = asyncio.create_task(svc.sync_scopes())
    try:
        await asyncio.wait_for(paused.wait(), _WAIT)
        assert len(git_ops.fetches) == 1, "phase 1 did not fetch the clone"
        origin.create_head("new")
        # What a bundle request for s-new publishes (scopes/api.py).
        await watcher.trigger(None, {"scope_id": "s-new", "honor_backoff": True})
    finally:
        resume.set()
        await asyncio.wait_for(sync_pass, _WAIT)

    assert len(git_ops.fetches) == 2
    fetcher = GitPolicyFetcher(tmp_path / "opal", "s-new", scopes[2].policy)
    assert fetcher.has_branch_ref()


# --- the missing-branch ERROR -------------------------------------------------


@pytest.mark.asyncio
async def test_a_pass_logs_a_missing_branch_once_however_many_scopes_name_it(
    tmp_path,
):
    """Once per branch and per pass: the next pass logs it again."""
    origin = _origin(tmp_path / "origin")
    scopes = [_scope("s-main", origin)]
    scopes += [_scope(f"x{i}", origin, "gone-x") for i in range(3)]
    scopes += [_scope(f"y{i}", origin, "gone-y") for i in range(2)]
    svc = _service(tmp_path, scopes)
    await svc.sync_scope(scope_id="s-main")

    for _ in range(2):
        with capture_records() as logs:
            await svc.sync_scopes()
        assert _missing_branch_errors(logs.emitted) == {"gone-x": 1, "gone-y": 1}


@pytest.mark.asyncio
async def test_a_branch_missing_from_two_clones_is_logged_once_for_each(tmp_path):
    a, b = _origin(tmp_path / "a"), _origin(tmp_path / "b")
    scopes = [_scope("a-main", a), _scope("b-main", b)]
    scopes += [_scope(f"a{i}", a, "production") for i in range(2)]
    scopes += [_scope(f"b{i}", b, "production") for i in range(2)]
    svc = _service(tmp_path, scopes)

    with capture_records() as logs:
        await svc.sync_scopes()

    assert _missing_branch_errors(logs.emitted) == {"production": 2}
    assert sorted(
        r["message"] for r in logs.emitted if r["message"].startswith(_MISSING)
    ) == sorted(
        f"{_MISSING}production ({origin.working_tree_dir})" for origin in (a, b)
    )


@pytest.mark.parametrize(
    "failure",
    ["remote hung up", TimeoutError("git fetch exceeded 60s")],
    ids=["remote", "timeout"],
)
@pytest.mark.asyncio
async def test_a_pass_whose_fetch_failed_reports_no_branch_missing_on_the_remote(
    tmp_path, git_ops, failure
):
    """Phase 1's fetch of the clone fails, and the clone's phase-2 scope whose
    branch it lacks does not fetch it again: the pass never reached the
    remote, which has the branch. That scope's sync says so at DEBUG, and no
    "Did not find target branch on remote"; the fetch's own failure is
    logged. The refresh-all pass, which does not honour the backoff, so
    that phase 2 does sync the scope.

    Mutation: reporting the missing branch whatever the pass's fetch ended
    in logs the ERROR for a branch the remote has.
    """
    origin = _origin(tmp_path / "origin")
    svc = _service(tmp_path, [_scope("s-main", origin), _scope("s-new", origin, "new")])
    await svc.sync_scope(scope_id="s-main")
    origin.create_head("new")
    git_ops.fail.append(failure)

    with capture_records() as logs:
        await svc.sync_scopes(honor_backoff=False)

    assert len(git_ops.fetches) == 1
    assert _missing_branch_errors(logs.emitted) == {}
    assert [
        r["message"]
        for r in logs.emitted
        if r["level"].name == "DEBUG" and "is not in the clone" in r["message"]
    ] == [
        f"scope s-new: target branch new is not in the clone of "
        f"{origin.working_tree_dir}, and no fetch of it in this sync pass reached "
        "the remote"
    ]


# --- phase 2: one slot per clone ----------------------------------------------


@pytest.mark.asyncio
async def test_a_blocked_clone_holds_one_phase_two_slot_and_the_other_clones_finish(
    tmp_path, monkeypatch
):
    """Phase 2 with two slots, clone a's scopes first in line, and a's lock
    held by something slow (a long fetch holds it the same way) from the
    start of phase 2: b's and c's scopes all finish while a waits; a waits in
    one slot, with as many of its scopes waiting at its lock at once as phase
    2 runs per clone (one more is on a).

    Mutations: one task per scope, each taking a slot, puts a1 and a2 in
    both slots, and no other scope runs until a's lock is released; one scope
    at a time per clone leaves a single one of a's scopes at the lock, and no
    bound leaves all of them there.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 2)
    lanes = _SCOPES_IN_FLIGHT_PER_CLONE
    origins = {name: _origin(tmp_path / name) for name in "abc"}
    scopes = [_scope(f"{name}0", origins[name]) for name in "abc"]
    scopes += [_scope(f"a{i}", origins["a"]) for i in range(1, lanes + 2)]
    scopes += [_scope(f"{name}{i}", origins[name]) for name in "bc" for i in (1, 2)]
    svc = _service(tmp_path, scopes)
    a_clone = GitPolicyFetcher.source_id(scopes[0].policy)
    a_scopes = {f"a{i}" for i in range(1, lanes + 2)}
    others = {"b1", "b2", "c1", "c2"}

    held, release, others_done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    holder = None

    async def hold_a():
        async with GitPolicyFetcher.lock_source(a_clone):
            held.set()
            await release.wait()

    in_sync = collections.Counter()
    peak = collections.Counter()
    slots = collections.defaultdict(set)
    done = set()
    real_sync_scope = svc.sync_scope
    real_concurrently = svc._sync_scopes_concurrently

    async def sync_scopes_concurrently(groups, semaphore, **kwargs):
        if not kwargs["force_fetch"]:
            semaphore = _NumberedSlots(semaphore)
        return await real_concurrently(groups, semaphore, **kwargs)

    async def sync_scope(**kwargs):
        nonlocal holder
        scope_id = kwargs["scope_id"]
        if kwargs["force_fetch"]:
            return await real_sync_scope(**kwargs)
        if holder is None:
            holder = asyncio.create_task(hold_a())
        await held.wait()
        clone = scope_id[0]
        slots[clone].add(_slot.get())
        in_sync[clone] += 1
        peak[clone] = max(peak[clone], in_sync[clone])
        try:
            return await real_sync_scope(**kwargs)
        finally:
            in_sync[clone] -= 1
            done.add(scope_id)
            if others <= done:
                others_done.set()

    monkeypatch.setattr(svc, "_sync_scopes_concurrently", sync_scopes_concurrently)
    monkeypatch.setattr(svc, "sync_scope", sync_scope)

    sync_pass = asyncio.create_task(svc.sync_scopes())
    try:
        try:
            await asyncio.wait_for(others_done.wait(), _WAIT)
        except asyncio.TimeoutError:
            pytest.fail(
                f"with a's lock held, only {sorted(done)} finished; "
                f"slots per clone: {dict(slots)}"
            )
        assert not sync_pass.done()
        assert done & a_scopes == set()
        assert in_sync["a"] == lanes
        assert len(slots["a"]) == 1
    finally:
        release.set()
        await asyncio.wait_for(sync_pass, _WAIT)
        if holder is not None:
            await holder

    assert done == a_scopes | others
    assert {clone: len(numbers) for clone, numbers in slots.items()} == {
        "a": 1,
        "b": 1,
        "c": 1,
    }
    assert peak["a"] == lanes


# More scopes on the clone than phase 2 runs at once in its slot, so that some
# are still to start when s1 fails.
_MANY = 2 * _SCOPES_IN_FLIGHT_PER_CLONE + 2


@pytest.mark.asyncio
async def test_a_scope_deleted_mid_group_does_not_skip_the_rest_of_its_clone(
    tmp_path,
):
    origin = _origin(tmp_path / "origin")
    scopes = [_scope(f"s{i}", origin) for i in range(_MANY)]
    pubsub = _PubSub()
    svc = ScopesService(
        base_dir=tmp_path / "opal",
        scopes=_Scopes(scopes, deleted={"s1"}),
        pubsub_endpoint=pubsub,
    )

    await svc.sync_scopes()

    assert pubsub.notified_scopes() == {f"s{i}" for i in range(_MANY)} - {"s1"}


@pytest.mark.asyncio
async def test_a_scope_whose_sync_raises_mid_group_does_not_skip_the_rest_of_its_clone(
    tmp_path, monkeypatch
):
    origin = _origin(tmp_path / "origin")
    scopes = [_scope(f"s{i}", origin) for i in range(_MANY)]
    pubsub = _PubSub()
    svc = _service(tmp_path, scopes, pubsub)
    real_sync_scope = svc.sync_scope

    async def sync_scope(**kwargs):
        if kwargs["scope_id"] == "s1":
            raise RuntimeError("store hiccup")
        return await real_sync_scope(**kwargs)

    monkeypatch.setattr(svc, "sync_scope", sync_scope)

    with capture_records() as logs:
        await svc.sync_scopes()

    assert pubsub.notified_scopes() == {f"s{i}" for i in range(_MANY)} - {"s1"}
    errors = [r["message"] for r in logs.emitted if r["level"].name == "ERROR"]
    assert errors == ["sync_scope failed for s1: RuntimeError: store hiccup"]


@pytest.mark.asyncio
async def test_a_scope_repointed_after_the_pass_listed_it_is_left_to_its_repoint(
    tmp_path, git_ops
):
    """The pass syncs a scope in the group of the clone it listed it under. A
    scope a PUT moved to another repository since then is skipped there, at
    DEBUG: the repoint's own sync handles it.

    Mutation: syncing it anyway clones the new repository in the old clone's
    slot.
    """
    a, b = _origin(tmp_path / "a"), _origin(tmp_path / "b")
    scopes = [_scope("s0", a), _scope("s1", a)]
    pubsub = _PubSub()
    svc = ScopesService(
        base_dir=tmp_path / "opal",
        scopes=_Scopes(scopes, moved={"s1": _scope("s1", b)}),
        pubsub_endpoint=pubsub,
    )

    with capture_records() as logs:
        await svc.sync_scopes()

    assert git_ops.clones == [a.working_tree_dir]
    assert pubsub.notified_scopes() == {"s0"}
    skipped = [
        r
        for r in logs.emitted
        if r["level"].name == "DEBUG"
        and r["message"].startswith("Skipping scope s1 in this sync pass")
    ]
    assert len(skipped) == 1


@pytest.mark.asyncio
async def test_a_scope_moved_to_another_branch_after_the_pass_listed_it_gets_it(
    tmp_path, git_ops
):
    """A pass's fetch asks for the branches the scopes it listed track, and
    for the branch of the scope it syncs as that scope reads now: a scope a
    PUT moved to another branch of its clone since the pass read the store is
    synced on its new branch, which that fetch brings.

    Mutation: leaving the syncing scope's own branch out of a pass's fetch
    (the git command line) leaves the new branch missing.
    """
    origin = _origin(tmp_path / "origin")
    origin.create_head("old")
    moved = _scope("s-x", origin, "new")
    pubsub = _PubSub()
    svc = ScopesService(
        base_dir=tmp_path / "opal",
        scopes=_Scopes([_scope("s-x", origin, "old")], moved={"s-x": moved}),
        pubsub_endpoint=pubsub,
    )
    await svc.sync_scope(scope_id="s-x")
    origin.create_head("new")

    await svc.sync_scopes()

    assert len(git_ops.fetches) == 1
    assert GitPolicyFetcher(tmp_path / "opal", "s-x", moved.policy).has_branch_ref()
    assert "s-x" in pubsub.notified_scopes()


# --- the pass context -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pass_records_its_start_for_its_own_syncs_only():
    """GitPolicyFetcher.current_pass_started() is the start of the pass the
    calling task runs in, and None outside one, a task running beside the pass
    included."""
    go = asyncio.Event()

    async def pass_started(after=None):
        if after is not None:
            await after.wait()
        return GitPolicyFetcher.current_pass_started()

    beside = asyncio.create_task(pass_started(after=go))
    before = datetime.datetime.now()
    with GitPolicyFetcher.sync_pass():
        started = GitPolicyFetcher.current_pass_started()
        inside = await asyncio.create_task(pass_started())
        go.set()
        beside_saw = await beside
    assert before <= started <= datetime.datetime.now()
    assert inside == started
    assert beside_saw is None
    assert GitPolicyFetcher.current_pass_started() is None


@pytest.mark.asyncio
async def test_a_task_that_outlives_its_pass_is_no_longer_in_it():
    """A task started in a pass keeps the pass in its context after the pass
    ended. It must not use the pass's start, nor log a missing branch once per
    pass for a pass that is over.

    Mutation: not marking the pass ended gives the task the pass's start, and
    its second missing-branch report is dropped as a repeat.
    """
    source = GitPolicyScopeSource(
        source_type="git", url="https://git/a.git", branch="gone", auth=NoAuthData()
    )
    fetcher = GitPolicyFetcher(Path("/unused"), "s", source)
    go = asyncio.Event()

    async def straggler():
        await go.wait()
        fetcher._report_missing_branch()
        fetcher._report_missing_branch()
        return GitPolicyFetcher.current_pass_started()

    with GitPolicyFetcher.sync_pass():
        task = asyncio.create_task(straggler())
        await asyncio.sleep(0)
    go.set()
    with capture_records() as logs:
        started = await task

    assert started is None
    assert _missing_branch_errors(logs.emitted) == {"gone": 2}


def test_a_fetch_that_started_when_the_pass_did_is_not_one_of_the_pass():
    """A clone whose last fetch started at the pass's start, to the
    microsecond, was not fetched in the pass, as _should_fetch counts it too:
    its missing branch is logged at DEBUG. A fetch one microsecond later is one
    of the pass, and the branch is logged as missing on the remote.

    Mutation: comparing with < instead of <= takes the fetch at the pass's
    start for one of the pass, and logs the ERROR.
    """
    source = GitPolicyScopeSource(
        source_type="git", url="https://git/a.git", branch="gone", auth=NoAuthData()
    )
    fetcher = GitPolicyFetcher(Path("/unused"), "s", source)
    last_fetched = GitPolicyFetcher.repos_last_fetched

    with GitPolicyFetcher.sync_pass():
        started = GitPolicyFetcher.current_pass_started()
        last_fetched[fetcher._source_id] = started
        with capture_records() as at_start:
            fetcher._report_missing_branch()
        last_fetched[fetcher._source_id] = started + datetime.timedelta(microseconds=1)
        with capture_records() as after_start:
            fetcher._report_missing_branch()

    assert _missing_branch_errors(at_start.emitted) == {}
    assert [
        (r["level"].name, r["message"])
        for r in at_start.emitted
        if "is not in the clone" in r["message"]
    ] == [
        (
            "DEBUG",
            "scope s: target branch gone is not in the clone of https://git/a.git, "
            "and no fetch of it in this sync pass reached the remote",
        )
    ]
    assert _missing_branch_errors(after_start.emitted) == {"gone": 1}


def test_a_pass_closed_outside_its_context_still_leaves_the_in_flight_count():
    """A pass coroutine can be closed outside its task's context (the garbage
    collector closing one whose loop is gone), where the pass's context cannot
    be reset. It must still leave _sync_passes_in_flight, or no repack runs in
    this process again.

    Mutation: resetting the context before the count is decremented leaves
    the count at 1.
    """

    async def a_pass():
        with GitPolicyFetcher.sync_pass():
            await asyncio.sleep(0)

    coro = a_pass()
    contextvars.copy_context().run(coro.send, None)
    assert git_fetcher._sync_passes_in_flight == 1

    with contextlib.suppress(ValueError):
        coro.close()

    assert git_fetcher._sync_passes_in_flight == 0
