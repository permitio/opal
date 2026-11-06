"""The git command-line fetch (SCOPES_GIT_FETCH_WITH_CLI) inside a scopes sync
pass: the lanes of a clone's scopes, two passes side by side and the refreshes
asked for meanwhile never find a clone's lock held by one another; a pass
fetches or clones each clone once, whatever the op ends in and whether the
pass honours the backoff or not, and its fetch of a clone does not stand in for
the clone a phase-2 scope that finds it invalid makes (with libgit2 too); a
fetch that fails on this server still lets the scope be checked against what
its clone holds; a scope whose branch did not move gets no ref write; and a
git that hangs ends phase 1 at its timeout plus the kill grace.

Real git against local origins (see git_cli_test).
"""

import asyncio
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import git
import pygit2
import pytest
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_common.tests.log_capture import capture_records
from opal_server import git_cli, git_fetcher
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

_AUTHOR = git.Actor("test", "test@example.com")


class _Scopes:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        return list(self._scopes.values())


class _PubSub:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append(list(topics))

    def notified(self):
        return {t.split(":", 1)[0] for topics in self.published for t in topics}


def _commit(origin: git.Repo, text: str) -> None:
    (Path(origin.working_tree_dir) / "policy" / "a.rego").write_text(text)
    origin.index.add(["policy/a.rego"])
    origin.index.commit(text, author=_AUTHOR, committer=_AUTHOR)


def _origin(path: Path) -> git.Repo:
    repo = git.Repo.init(path, initial_branch="main")
    (path / "policy").mkdir()
    _commit(repo, "package a\n")
    return repo


def _scope(scope_id: str, url: str, branch: str = "main") -> Scope:
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git", url=url, branch=branch, auth=NoAuthData()
        ),
    )


def _service(tmp_path: Path, scopes, pubsub=None) -> ScopesService:
    return ScopesService(
        base_dir=tmp_path / "opal",
        scopes=_Scopes(scopes),
        pubsub_endpoint=pubsub if pubsub is not None else _PubSub(),
    )


@pytest.fixture(autouse=True)
def _state(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", 0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)
    monkeypatch.setattr(git_fetcher, "_repacks_due", {})
    monkeypatch.setattr(git_fetcher, "_sync_passes_in_flight", 0)
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    yield
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()


class _Ops:
    """The git command-line fetches and clones tried, counted where the fetcher
    calls git_cli.

    ``fail``: an error every fetch (or clone) tried
    then fails with, after its on_gone, as git_cli's do.
    """

    def __init__(self):
        self.fetches = 0
        self.clones = 0
        self.fail_fetch = None
        self.fail_clone = None


@pytest.fixture
def ops(monkeypatch):
    calls = _Ops()
    real_fetch, real_clone = git_fetcher.cli_fetch, git_fetcher.cli_clone

    async def fetch(*args, **kwargs):
        calls.fetches += 1
        if calls.fail_fetch is not None:
            kwargs["on_gone"](False)
            raise calls.fail_fetch
        return await real_fetch(*args, **kwargs)

    async def clone(*args, **kwargs):
        calls.clones += 1
        if calls.fail_clone is not None:
            kwargs["on_gone"](False)
            raise calls.fail_clone
        return await real_clone(*args, **kwargs)

    monkeypatch.setattr(git_fetcher, "cli_fetch", fetch)
    monkeypatch.setattr(git_fetcher, "cli_clone", clone)
    return calls


@pytest.fixture
def emitted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        metrics, "increment", lambda m, tags=None: calls.append((m, tags))
    )
    monkeypatch.setattr(metrics, "gauge", lambda m, v, tags=None: None)
    return calls


def _scopes(origin: git.Repo, on_main: int, on_missing: int):
    url = origin.working_tree_dir
    return [_scope(f"m{i}", url) for i in range(on_main)] + [
        _scope(f"g{i}", url, f"gone-{i}") for i in range(on_missing)
    ]


@pytest.mark.asyncio
async def test_lanes_passes_and_refreshes_never_find_a_clone_locked_by_each_other(
    tmp_path, ops, emitted
):
    """Up to _SCOPES_IN_FLIGHT_PER_CLONE scopes of a clone at once, two passes
    side by side, and refreshes of single scopes during them: every git op of
    one process on a clone runs under that clone's lock_source, so none finds
    the clone's lock held (which would skip its scope), and every scope on an
    existing branch is synced."""
    origin = _origin(tmp_path / "origin")
    pubsub = _PubSub()
    svc = _service(tmp_path, _scopes(origin, 12, 12), pubsub)
    await svc.sync_scope(scope_id="m0")
    _commit(origin, "package b\n")

    await asyncio.gather(
        svc.sync_scopes(),
        svc.sync_scopes(),
        *(svc.sync_scope(scope_id=f"m{i}", force_fetch=True) for i in range(6)),
        *(svc.sync_scope(scope_id=f"g{i}", honor_backoff=True) for i in range(6)),
    )

    assert [t for _, t in emitted if t == {"reason": "clone_busy"}] == []
    assert {f"m{i}" for i in range(12)} <= pubsub.notified()


# (failure, whether it backs the source off); None is a success.
_OUTCOMES = pytest.mark.parametrize(
    "failure, backed_off",
    [
        (None, False),
        (git_cli.GitCliError(128, "fatal: the remote said no"), True),
        (git_cli.GitCliTimeoutError("git fetch exceeded 60s"), True),
        (git_cli.GitCliLocalError(127, "git not found on PATH"), False),
        (git_cli.GitCliBusyError(128, "fatal: another git op holds it"), False),
        (git_cli.GitCliRefusedSourceError(128, "fatal: a credential in the URL"), True),
    ],
    ids=["success", "remote", "timeout", "local", "busy", "refused"],
)

# How the pass honours the source backoff: as the periodic pass does, not at
# all (the refresh-all pass), or with the backoff turned off.
_BACKOFF = pytest.mark.parametrize("backoff", ["pass", "refresh-all", "off"])


def _pass(svc: ScopesService, backoff: str, monkeypatch):
    if backoff == "off":
        monkeypatch.setattr(opal_server_config, "SCOPES_GIT_BACKOFF_BASE_SECONDS", 0)
    return svc.sync_scopes(honor_backoff=backoff != "refresh-all")


def _logged(records) -> list:
    return [
        r["message"]
        for r in records.deployed
        if r["level"].name in ("ERROR", "WARNING")
        and "Did not find target branch" not in r["message"]
    ]


def _lines_of_one_attempt(failure, backed_off: bool, backoff: str) -> int:
    """What one op that ends in ``failure`` logs at WARNING or above: its
    failure, and the backoff's own line for a source it backs off."""
    if failure is None:
        return 0
    return 1 + (1 if backed_off and backoff != "off" else 0)


@_BACKOFF
@_OUTCOMES
@pytest.mark.asyncio
async def test_a_pass_fetches_each_clone_once_whatever_the_fetch_ends_in(
    failure, backed_off, backoff, tmp_path, ops, emitted, monkeypatch
):
    """Phase 1 fetches the clone; the scopes of the clone whose branches it
    lacks would each fetch it again in phase 2 (it was not fetched in this
    pass), and fail, and log it, once more: with the backoff not in the way, a
    hung source's every one to its timeout.

    A pass fetches each clone once; the next fetches it again, unless
    the source is backed off.
    """
    origin = _origin(tmp_path / "origin")
    svc = _service(tmp_path, _scopes(origin, 3, 5))
    await svc.sync_scope(scope_id="m0")
    ops.fetches = 0
    ops.fail_fetch = failure

    with capture_records() as records:
        await _pass(svc, backoff, monkeypatch)
    first = ops.fetches
    await _pass(svc, backoff, monkeypatch)

    assert first == 1
    assert ops.fetches - first == (0 if backed_off and backoff == "pass" else 1)
    assert len(_logged(records)) == _lines_of_one_attempt(failure, backed_off, backoff)


@_BACKOFF
@_OUTCOMES
@pytest.mark.asyncio
async def test_a_pass_clones_each_clone_once_whatever_the_clone_ends_in(
    failure, backed_off, backoff, tmp_path, ops, emitted, monkeypatch
):
    """No clone on disk: each of the source's 21 scopes would clone it, one
    after another, and log its failure. A pass tries once, and logs what
    one attempt logs."""
    origin = _origin(tmp_path / "origin")
    svc = _service(tmp_path, _scopes(origin, 21, 0))
    ops.fail_clone = failure

    with capture_records() as records:
        await _pass(svc, backoff, monkeypatch)
    first = ops.clones
    if failure is not None:
        await _pass(svc, backoff, monkeypatch)

    assert first == 1
    assert len(_logged(records)) == _lines_of_one_attempt(failure, backed_off, backoff)
    if failure is not None:
        assert ops.clones - first == (0 if backed_off and backoff == "pass" else 1)


@pytest.mark.parametrize("what", ["invalid clone", "not a clone"])
@pytest.mark.asyncio
async def test_a_pass_tries_once_to_delete_a_clone_a_git_op_holds(
    what, tmp_path, emitted
):
    """The delete before a clone (an invalid clone's, or what is in the way of
    one), skipped while a git op holds the clone, is tried once a pass, not
    once for each scope of the source."""
    origin = _origin(tmp_path / "origin")
    svc = _service(tmp_path, _scopes(origin, 6, 0))
    clone = GitPolicyFetcher.repo_clone_path(
        tmp_path / "opal", _scope("m0", origin.working_tree_dir).policy
    )
    if what == "invalid clone":
        await svc.sync_scopes()
        GitPolicyFetcher.reset_caches()
        # Every object gone, the refs intact: an invalid clone.
        objects = clone / ".git" / "objects"
        for pack in (objects / "pack").iterdir():
            pack.unlink()
        for loose in objects.iterdir():
            if len(loose.name) == 2:
                shutil.rmtree(loose)
    else:
        clone.mkdir(parents=True)
        (clone / "file").write_text("x")
    # A lock fd of its own: to the delete, an op of another process.
    held = git_cli.take_clone_lock(clone)
    assert held is not None
    emitted.clear()
    try:
        with capture_records() as records:
            await svc.sync_scopes()
    finally:
        git_cli.drop_clone_lock(held)

    assert clone.exists()
    assert [t for _, t in emitted if t == {"reason": "clone_busy"}] == [
        {"reason": "clone_busy"}
    ]
    assert [
        r["message"]
        for r in records.deployed
        if r["message"].startswith("Not deleting")
    ] == [
        f"Not deleting {clone} for scope m0: a git op of another process holds its lock"
    ]


def _overwrite_object(clone: Path, oid: str, with_oid: str) -> None:
    """Put ``with_oid``'s object file in place of ``oid``'s, once the clone's
    packs are unpacked into object files: ``oid`` is still in the clone, so a
    fetch does not download it again, but it reads as another object.

    Replaced, not written to: a clone of a local origin hard-links the
    origin's object files.
    """
    objects = clone / ".git" / "objects"
    for pack in sorted((objects / "pack").glob("*.pack")):
        data = pack.read_bytes()
        for part in (objects / "pack").glob(f"{pack.stem}.*"):
            part.unlink()
        subprocess.run(
            ["git", "-C", str(clone), "unpack-objects", "-q"], input=data, check=True
        )
    target = objects / oid[:2] / oid[2:]
    target.unlink()
    target.write_bytes((objects / with_oid[:2] / with_oid[2:]).read_bytes())


def _readable(clone: Path, oid: str) -> bool:
    repo = pygit2.Repository(str(clone))
    try:
        return repo.get(oid) is not None
    except pygit2.GitError:
        return False
    finally:
        repo.free()


@pytest.mark.parametrize("cli", [False, True], ids=["libgit2", "cli"])
@pytest.mark.asyncio
async def test_a_pass_re_clones_a_clone_only_a_phase_2_scope_finds_invalid(
    cli, tmp_path, monkeypatch
):
    """Phase 1's scope of the clone reads its branch, and phase 1 fetches the
    clone; the phase-2 scope whose branch head cannot be read finds the clone
    invalid. That fetch is not the pass's clone of it: the scope deletes the
    clone and clones it again, in the same pass.

    Mutation: one record of the sources a pass fetched or cloned, as
    before, leaves the clone invalid pass after pass.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    origin = _origin(tmp_path / "origin")
    on_main = origin.head.commit.hexsha
    origin.create_head("other").checkout()
    _commit(origin, "package other\n")
    on_other = origin.head.commit.hexsha
    origin.heads.main.checkout()
    url = origin.working_tree_dir
    svc = _service(tmp_path, [_scope("m0", url), _scope("o0", url, "other")])
    await svc.sync_scopes()
    clone = GitPolicyFetcher.repo_clone_path(
        tmp_path / "opal", _scope("m0", url).policy
    )
    GitPolicyFetcher.reset_caches()
    _overwrite_object(clone, on_other, on_main)
    # The premise: the origin is intact, the clone reads one branch only.
    assert _readable(Path(url), on_other)
    assert _readable(clone, on_main) and not _readable(clone, on_other)

    with capture_records() as records:
        await svc.sync_scopes()

    assert _readable(clone, on_other)
    assert [
        r["message"] for r in records.deployed if r["message"].startswith("Deleting")
    ] == [f"Deleting invalid repo: {clone}"]


@pytest.mark.asyncio
async def test_a_hung_fetch_holds_a_refresh_all_pass_for_one_timeout_not_one_per_scope(
    tmp_path, blackhole, monkeypatch, ops
):
    """The refresh-all pass does not honour the backoff: without the pass's
    record of the clones it fetched, each scope of a hung source whose branch
    its clone lacks would fetch it again in phase 2, to its timeout."""
    timeout, grace = 1.0, 0.5
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", timeout)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", grace)
    origin = _origin(tmp_path / "origin")
    url = f"http://127.0.0.1:{blackhole}/hung-{uuid.uuid4().hex}.git"
    scopes = [_scope("m0", url)] + [_scope(f"g{i}", url, f"gone-{i}") for i in range(5)]
    clone = GitPolicyFetcher.repo_clone_path(tmp_path / "opal", scopes[0].policy)
    clone.parent.mkdir(parents=True, exist_ok=True)
    repo = pygit2.clone_repository(origin.working_tree_dir, str(clone))
    try:
        repo.remotes.set_url("origin", url)
    finally:
        repo.free()
    svc = _service(tmp_path, scopes)

    start = time.monotonic()
    await svc.sync_scopes(honor_backoff=False)
    elapsed = time.monotonic() - start

    assert ops.fetches == 1
    assert elapsed <= timeout + grace + 3


@pytest.mark.parametrize(
    "failure",
    [
        git_cli.GitCliLocalError(127, "git not found on PATH"),
        git_cli.GitCliBusyError(128, "fatal: another git op holds it"),
    ],
    ids=["local", "busy"],
)
@pytest.mark.asyncio
async def test_a_fetch_that_fails_on_this_server_still_checks_the_clone_for_changes(
    failure, tmp_path, ops
):
    """What the clone already holds (a fetch of another process, say) is not
    held back from the scope because this sync's own fetch could not run."""
    origin = _origin(tmp_path / "origin")
    pubsub = _PubSub()
    svc = _service(tmp_path, _scopes(origin, 1, 0), pubsub)
    await svc.sync_scope(scope_id="m0")
    _commit(origin, "package b\n")
    clone = GitPolicyFetcher.repo_clone_path(
        tmp_path / "opal", _scope("m0", origin.working_tree_dir).policy
    )
    repo = pygit2.Repository(str(clone))
    try:
        repo.remotes["origin"].fetch()  # another process's fetch
    finally:
        repo.free()
    head = origin.head.commit.hexsha
    published = len(pubsub.published)
    ops.fail_fetch = failure

    await svc.sync_scope(scope_id="m0", force_fetch=True)

    assert ops.fetches == 1
    assert len(pubsub.published) > published
    fresh = pygit2.Repository(str(clone))
    try:
        assert str(fresh.references["refs/heads/scopes/m0"].target) == head
    finally:
        fresh.free()


@pytest.mark.parametrize(
    "failure",
    [
        git_cli.GitCliLocalError(127, "git not found on PATH"),
        git_cli.GitCliBusyError(128, "fatal: another git op holds it"),
    ],
    ids=["local", "busy"],
)
@pytest.mark.asyncio
async def test_a_pass_says_it_fetches_for_a_missing_branch_only_when_it_does(
    failure, tmp_path, ops
):
    """A phase-1 fetch that failed on this server leaves neither a fetch time
    nor a backoff, so a phase-2 scope whose branch the clone lacks asks for a
    fetch: the pass does not fetch the clone again for it, and does not say
    it does. Nor that the remote lacks the branch, since nothing in the pass
    reached the remote: each such scope says at DEBUG that its branch is not
    in the clone, naming the source.

    Mutation: logging before the pass's check says "re-fetching the
    remote" for each such scope; reporting a missing branch whatever the
    fetch ended in logs "Did not find target branch on remote" for each.
    """
    origin = _origin(tmp_path / "origin")
    svc = _service(tmp_path, _scopes(origin, 1, 2))
    await svc.sync_scope(scope_id="m0")
    ops.fetches = 0
    ops.fail_fetch = failure

    with capture_records() as records:
        await svc.sync_scopes()

    assert ops.fetches == 1
    deployed = [r["message"] for r in records.deployed]
    assert [m for m in deployed if m.startswith("Target branch was not found")] == []
    assert [m for m in deployed if m.startswith("Did not find target branch")] == []
    url = origin.working_tree_dir
    emitted = [r["message"] for r in records.emitted]
    assert sorted(m for m in emitted if "is not in the clone" in m) == [
        f"scope g{i}: target branch gone-{i} is not in the clone of {url}, and no "
        "fetch of it in this sync pass reached the remote"
        for i in range(2)
    ]


@pytest.mark.parametrize(
    "failure",
    [
        git_cli.GitCliLocalError(127, "git not found on PATH"),
        git_cli.GitCliBusyError(128, "fatal: another git op holds it"),
    ],
    ids=["local", "busy"],
)
@pytest.mark.asyncio
async def test_a_fetch_that_fails_on_this_server_marks_no_repack(
    failure, tmp_path, ops, monkeypatch
):
    """A sync whose fetch could not run on this server wrote no pack, so it
    does not mark the clone due for a repack, even with the clone at the pack
    limit; the sync of the same clone whose fetch runs does.

    Mutation: marking after every sync that wanted to fetch marks it.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", 2)
    origin = _origin(tmp_path / "origin")
    svc = _service(tmp_path, _scopes(origin, 1, 0))
    await svc.sync_scope(scope_id="m0")
    for text in ("package b\n", "package c\n"):
        _commit(origin, text)
        await svc.sync_scope(scope_id="m0", force_fetch=True)
    policy = _scope("m0", origin.working_tree_dir).policy
    clone = GitPolicyFetcher.repo_clone_path(tmp_path / "opal", policy)
    assert git_fetcher._count_pack_files(clone) >= 2  # the premise
    assert set(git_fetcher._repacks_due) == {GitPolicyFetcher.source_id(policy)}
    git_fetcher._repacks_due.clear()
    _commit(origin, "package d\n")
    ops.fetches = 0
    ops.fail_fetch = failure

    await svc.sync_scope(scope_id="m0", force_fetch=True)

    assert ops.fetches == 1
    assert git_fetcher._repacks_due == {}


def _branch_file(clone: Path, scope_id: str) -> tuple:
    """The scope's branch file in the clone, as (inode, mtime, content): a
    write of the branch replaces the file."""
    path = clone / ".git" / "refs" / "heads" / "scopes" / scope_id
    stat = path.stat()
    return stat.st_ino, stat.st_mtime_ns, path.read_text().strip()


@pytest.mark.asyncio
async def test_a_pass_writes_a_scope_s_branch_only_once_it_has_moved(tmp_path):
    """Every pass checks every scope against its clone.

    A scope whose branch did not move gets no ref write; one whose
    branch moved does. A write of a branch to the value it already has
    rewrites nothing, but takes its lock all the same, which shows in
    the mtime of the directory the lock file goes in.
    """
    origin = _origin(tmp_path / "origin")
    svc = _service(tmp_path, _scopes(origin, 3, 0))
    await svc.sync_scopes()
    clone = GitPolicyFetcher.repo_clone_path(
        tmp_path / "opal", _scope("m0", origin.working_tree_dir).policy
    )
    branches = clone / ".git" / "refs" / "heads" / "scopes"
    before = [_branch_file(clone, f"m{i}") for i in range(3)]
    branches_before = branches.stat().st_mtime_ns

    await svc.sync_scopes()
    unchanged = [_branch_file(clone, f"m{i}") for i in range(3)]
    branches_unchanged = branches.stat().st_mtime_ns
    _commit(origin, "package b\n")
    await svc.sync_scopes()
    moved = [_branch_file(clone, f"m{i}") for i in range(3)]

    assert unchanged == before
    assert branches_unchanged == branches_before
    head = origin.head.commit.hexsha
    for (ino, mtime, content), (old_ino, old_mtime, _) in zip(moved, before):
        assert content == head
        assert (ino, mtime) != (old_ino, old_mtime)


@pytest.mark.asyncio
async def test_a_git_that_hangs_ends_phase_1_at_its_timeout_and_the_kill_grace(
    tmp_path, blackhole, monkeypatch, processes_with
):
    """A hung clone of one source holds phase 1, and with it every other
    clone's phase-2 scopes, until its timeout plus the kill grace: no
    longer."""
    timeout, grace = 1.0, 0.5
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", timeout)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", grace)
    origin = _origin(tmp_path / "origin")
    marker = f"hung-{uuid.uuid4().hex}"
    hung = _scope("hung", f"http://127.0.0.1:{blackhole}/{marker}.git")
    pubsub = _PubSub()
    svc = _service(tmp_path, [hung, *_scopes(origin, 4, 0)], pubsub)
    await svc.sync_scope(scope_id="m0")

    start = time.monotonic()
    await svc.sync_scopes()
    elapsed = time.monotonic() - start

    assert elapsed <= timeout + grace + 3
    assert {f"m{i}" for i in range(4)} <= pubsub.notified()
    assert processes_with(marker) == []
