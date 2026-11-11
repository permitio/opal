"""With the git command-line fetch (SCOPES_GIT_FETCH_WITH_CLI), a fetch asks
the remote only for the branches its syncs need.

A refresh, a PUT or a missing branch asks for its scope's branch; the syncs
that wait for the clone while its fetch runs share the next fetch, which asks
for all their branches; a sync pass asks for every branch its scopes track on
the clone, or for the whole refspec above
SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES (0: every fetch). Each branch is one
one-wildcard refspec, so over protocol v2 one ``ref-prefix`` line, and the
server lists only the branches that match. Each fetch records, per branch,
when it started, in the clone's .git/opal-fetched. libgit2 is unchanged.

Real git against a local ``git http-backend`` (conftest's git_http), whose
request bodies hold the ``ref-prefix`` lines git sent.
"""

import asyncio
import datetime
import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pygit2
import pytest
from opal_common.logger import logger
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server import git_cli, git_fetcher
from opal_server.config import opal_server_config
from opal_server.git_cli import (
    GitCliBusyError,
    GitCliLocalError,
    GitCliTimeoutError,
    cli_fetch,
    validate_git_cli_settings,
)
from opal_server.git_fetcher import GitConcurrencyLimitExceeded, GitPolicyFetcher
from opal_server.scopes.purge import purge_local_memory
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService

pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="needs git"),
    pytest.mark.fetch_backend("cli"),
]

_WAIT = 10.0
_MISSING = "Did not find target branch on remote: "


class _Scopes:
    def __init__(self, scopes):
        self.scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self.scopes:
            raise ScopeNotFoundError(scope_id)
        return self.scopes[scope_id]

    async def all(self):
        return list(self.scopes.values())


class _PubSub:
    async def publish(self, topics, data=None):
        pass


class _Fetches:
    """The git command-line fetches the fetcher starts, with their keyword
    arguments, through the real cli_fetch.

    ``hold_at``: the index of a fetch that waits for ``release`` before
    git starts (``entered`` is set then). ``refuse``: the indexes of the
    fetches the server refuses (git_http's ``error`` while they run), from
    ``refuse_from`` on all of them. ``raise_at``: index -> what that fetch
    raises instead of running git, as git_cli's own errors do, after its
    on_gone.
    """

    def __init__(self, server) -> None:
        self.server = server
        self.calls: List[dict] = []
        self.started: List[float] = []
        self.hold_at: Optional[int] = None
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.refuse: set = set()
        self.refuse_from: Optional[int] = None
        self.raise_at: Dict[int, BaseException] = {}


@pytest.fixture
def fetches(monkeypatch, git_http):
    recorded = _Fetches(git_http)
    real = git_fetcher.cli_fetch

    async def fetch(repo_path, remote, source, **kwargs):
        index = len(recorded.calls)
        recorded.calls.append(kwargs)
        recorded.started.append(time.monotonic())
        if index == recorded.hold_at:
            recorded.entered.set()
            try:
                await recorded.release.wait()
            except asyncio.CancelledError:
                kwargs["on_gone"](False)
                raise
        if index in recorded.raise_at:
            kwargs["on_gone"](False)
            raise recorded.raise_at[index]
        if index in recorded.refuse or (
            recorded.refuse_from is not None and index >= recorded.refuse_from
        ):
            git_http.error = "refused for the test"
        try:
            return await real(repo_path, remote, source, **kwargs)
        finally:
            git_http.error = None

    monkeypatch.setattr(git_fetcher, "cli_fetch", fetch)
    return recorded


@pytest.fixture(autouse=True)
def _state(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", 0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", False)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", 1000
    )
    monkeypatch.setattr(git_fetcher, "_repacks_due", {})
    monkeypatch.setattr(git_fetcher, "_sync_passes_in_flight", 0)
    monkeypatch.setattr(git_fetcher, "_fetch_marks_warned", set())
    monkeypatch.setattr(git_fetcher, "_unfetchable_branches_warned", set())
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    yield
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()


@pytest.fixture
def origin(git_http, make_origin):
    """The served origin: master, dev and feature/x."""
    return make_origin(git_http.root / "repo.git")


@pytest.fixture
def url(git_http, origin) -> str:
    return git_http.url("repo.git")


def _source(url: str, branch: str) -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git", url=url, branch=branch, auth=NoAuthData()
    )


def _scope(scope_id: str, url: str, branch: str) -> Scope:
    return Scope(scope_id=scope_id, policy=_source(url, branch))


def _scope_on(url: str, branch: str) -> Scope:
    return _scope(f"s-{branch.replace('/', '-')}", url, branch)


def _service(tmp_path: Path, scopes) -> ScopesService:
    return ScopesService(
        base_dir=tmp_path / "base", scopes=_Scopes(scopes), pubsub_endpoint=_PubSub()
    )


async def _refresh(service: ScopesService, scope_id: str) -> None:
    """What POST /scopes/{id}/refresh has the leader do (the watcher's
    trigger)."""
    await service.sync_scope(
        scope_id=scope_id, force_fetch=True, req_time=datetime.datetime.now()
    )


async def _missing_branch_sync(service: ScopesService, scope_id: str) -> None:
    """The sync a policy bundle request asks for when the scope's branch is not
    in its clone."""
    await service.sync_scope(
        scope_id=scope_id, req_time=datetime.datetime.now(), honor_backoff=True
    )


def _clone_path(tmp_path: Path, url: str) -> Path:
    return GitPolicyFetcher.repo_clone_path(tmp_path / "base", _source(url, "master"))


def _source_id(url: str) -> str:
    return GitPolicyFetcher.source_id(_source(url, "master"))


def _pkt_lines(body: bytes) -> List[bytes]:
    """The data of each pkt-line of ``body`` (flush and delimiter packets left
    out)."""
    lines, at = [], 0
    while at + 4 <= len(body):
        length = int(body[at : at + 4], 16)
        if length < 4:
            at += 4
            continue
        lines.append(body[at + 4 : at + length].rstrip(b"\n"))
        at += length
    return lines


def _listings(server) -> List[List[str]]:
    """The ref prefixes of each ls-refs request the server got, in order: one
    per fetch over protocol v2."""
    listings = []
    for body in server.bodies:
        lines = _pkt_lines(body)
        if b"command=ls-refs" not in lines:
            continue
        listings.append(
            [
                line[len(b"ref-prefix ") :].decode()
                for line in lines
                if line.startswith(b"ref-prefix ")
            ]
        )
    return listings


def _heads(branches) -> List[str]:
    return [f"refs/heads/{b}" for b in sorted(branches)]


def _remote_heads(clone: Path) -> Dict[str, str]:
    repo = pygit2.Repository(str(clone))
    try:
        prefix = "refs/remotes/origin/"
        return {
            name[len(prefix) :]: str(repo.references[name].target)
            for name in repo.references
            if name.startswith(prefix) and not name.endswith("/HEAD")
        }
    finally:
        repo.free()


def _pending(url: str) -> set:
    """The branches in the clone's batch."""
    return set(GitPolicyFetcher.pending_branches.get(_source_id(url), {}))


def _origin_head(origin, branch: str) -> str:
    return str(origin.repo.references[f"refs/heads/{branch}"].target)


def _mark(clone: Path, name: str) -> Path:
    return clone / ".git" / "opal-fetched" / name


def _branch_mark(clone: Path, branch: str) -> Path:
    return _mark(clone, hashlib.sha256(branch.encode()).hexdigest()[:32])


def _failed_mark(clone: Path, branch: str) -> Path:
    return _mark(clone, hashlib.sha256(branch.encode()).hexdigest()[:32] + ".failed")


async def _until(condition: Callable[[], bool]) -> None:
    deadline = asyncio.get_running_loop().time() + _WAIT
    while not condition():
        assert asyncio.get_running_loop().time() < deadline, "timed out"
        await asyncio.sleep(0.01)


@pytest.fixture
def records():
    seen = []
    sink = logger.add(lambda m: seen.append(m.record), level="DEBUG")
    yield seen
    logger.remove(sink)


async def _cloned(tmp_path, url, git_http, branches=("master",)):
    """A service for scopes on ``branches`` whose clone exists; the server's
    log of request bodies starts empty after it."""
    service = _service(tmp_path, [_scope_on(url, b) for b in branches])
    await service.sync_scope(scope_id=_scope_on(url, branches[0]).scope_id)
    assert _clone_path(tmp_path, url).is_dir()
    git_http.bodies.clear()
    return service


def _push(origin, *branches) -> Dict[str, str]:
    """A new commit on each branch (made when missing); its new head."""
    heads = {}
    for branch in branches:
        if f"refs/heads/{branch}" not in origin.repo.references:
            origin.branch(branch)
        heads[branch] = origin.commit(branch)
    return heads


# --- what one sync asks for -----------------------------------------------------


@pytest.mark.asyncio
async def test_a_refresh_asks_only_for_its_scopes_branch(
    tmp_path, url, origin, git_http, fetches
):
    service = await _cloned(tmp_path, url, git_http, ("master", "b1"))
    before = _remote_heads(_clone_path(tmp_path, url))
    pushed = _push(origin, "b1", "b2", "dev")

    await _refresh(service, "s-b1")

    assert _listings(git_http) == [["refs/heads/b1"]]
    assert _remote_heads(_clone_path(tmp_path, url)) == {**before, "b1": pushed["b1"]}


@pytest.mark.asyncio
async def test_a_missing_branch_is_fetched_alone(
    tmp_path, url, origin, git_http, fetches
):
    service = await _cloned(tmp_path, url, git_http, ("master", "nb"))
    pushed = _push(origin, "nb", "dev")

    await _missing_branch_sync(service, "s-nb")

    assert _listings(git_http) == [["refs/heads/nb"]]
    heads = _remote_heads(_clone_path(tmp_path, url))
    assert heads["nb"] == pushed["nb"]
    assert heads["dev"] != pushed["dev"]


@pytest.mark.asyncio
async def test_a_burst_of_syncs_for_a_branch_the_remote_lacks_costs_one_fetch(
    tmp_path, url, origin, git_http, fetches
):
    """A fetch that asked for the branch and started after a request stands in
    for that request's own fetch."""
    service = await _cloned(tmp_path, url, git_http, ("master", "nope"))
    asked = datetime.datetime.now()
    await _missing_branch_sync(service, "s-nope")

    await service.sync_scope(scope_id="s-nope", req_time=asked, honor_backoff=True)

    assert _listings(git_http) == [["refs/heads/nope"]]


@pytest.mark.asyncio
async def test_a_recent_fetch_of_another_branch_does_not_stand_in(
    tmp_path, url, origin, git_http, fetches
):
    """b1's fetch started after b2's refresh was asked for, but did not ask for
    b2: b2's refresh still fetches."""
    service = await _cloned(tmp_path, url, git_http, ("master", "b1", "b2"))
    pushed = _push(origin, "b1", "b2")
    asked = datetime.datetime.now()
    await _refresh(service, "s-b1")

    await service.sync_scope(scope_id="s-b2", force_fetch=True, req_time=asked)

    assert _listings(git_http) == [["refs/heads/b1"], ["refs/heads/b2"]]
    assert _remote_heads(_clone_path(tmp_path, url))["b2"] == pushed["b2"]


@pytest.mark.asyncio
async def test_a_branch_gone_from_the_remote_does_not_fail_the_fetch(
    tmp_path, url, origin, git_http, fetches, records
):
    """An exact refspec for a branch the remote lacks would fail the whole
    fetch, and with it every scope that shares the fetch; a pattern matches
    nothing."""
    service = await _cloned(tmp_path, url, git_http, ("master", "dev", "gone"))
    fetches.hold_at = 0
    pushed = _push(origin, "dev")
    first = asyncio.create_task(_refresh(service, "s-master"))
    await asyncio.wait_for(fetches.entered.wait(), _WAIT)
    rest = [asyncio.create_task(_refresh(service, s)) for s in ("s-dev", "s-gone")]
    await _until(lambda: _pending(url) == {"dev", "gone"})

    fetches.release.set()
    await asyncio.wait_for(asyncio.gather(first, *rest), _WAIT)

    assert _listings(git_http) == [["refs/heads/master"], _heads({"dev", "gone"})]
    assert _remote_heads(_clone_path(tmp_path, url))["dev"] == pushed["dev"]
    assert _source_id(url) not in GitPolicyFetcher.source_backoff
    missing = [r["message"] for r in records if r["message"].startswith(_MISSING)]
    assert len(missing) == 1 and missing[0].startswith(_MISSING + "gone ")


@pytest.mark.asyncio
async def test_a_branch_that_cannot_be_a_ref_is_not_asked_for(
    tmp_path, url, origin, git_http, fetches, records
):
    """No narrow fetch for it: the sync goes on to the change check on what the
    clone holds."""
    service = _service(
        tmp_path, [_scope("s-master", url, "master"), _scope("s-tilde", url, "x~1")]
    )
    await service.sync_scope(scope_id="s-master")

    await _refresh(service, "s-tilde")

    assert fetches.calls == []
    assert [r for r in records if r["message"].startswith(_MISSING + "x~1 ")]


def test_names_that_cannot_be_branches_are_left_out_of_a_pass_s_fetch(tmp_path):
    url = "https://git.example/repo.git"
    fetcher = GitPolicyFetcher(tmp_path, "s", _source(url, "own"))
    tracked = {_source_id(url): {"ok", "x~1", "has space", "a..b", ""}}

    with GitPolicyFetcher.sync_pass(tracked):
        assert fetcher._requested_branches() == frozenset({"ok", "own"})


def test_a_pass_with_no_name_that_can_be_a_branch_takes_the_whole_refspec(tmp_path):
    url = "https://git.example/repo.git"
    fetcher = GitPolicyFetcher(tmp_path, "s", _source(url, "x~1"))

    with GitPolicyFetcher.sync_pass({_source_id(url): {"x~1"}}):
        assert fetcher._requested_branches() is None
    assert fetcher._requested_branches() == frozenset()


def test_the_cap_is_the_most_branches_a_fetch_names(tmp_path, monkeypatch):
    url = "https://git.example/repo.git"
    fetcher = GitPolicyFetcher(tmp_path, "s", _source(url, "own"))
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", 2
    )

    with GitPolicyFetcher.sync_pass({_source_id(url): {"a"}}):
        assert fetcher._requested_branches() == frozenset({"a", "own"})
    with GitPolicyFetcher.sync_pass({_source_id(url): {"a", "b"}}):
        assert fetcher._requested_branches() is None


@pytest.mark.parametrize("length, can", [(1003, True), (1004, False)])
def test_a_branch_whose_tracking_ref_is_1024_bytes_cannot_be_asked_for(
    length, can, tmp_path
):
    """Refs/remotes/origin/ is 20 bytes: libgit2 looks up a ref of 1,023 bytes,
    and refuses one of 1,024 (ValueError)."""
    url = "https://git.example/repo.git"
    fetcher = GitPolicyFetcher(tmp_path, "s", _source(url, "b" * length))

    assert fetcher.branch_can_be_a_ref() is can
    assert fetcher._requested_branches() == (
        frozenset({"b" * length}) if can else frozenset()
    )


@pytest.mark.asyncio
async def test_a_stored_branch_too_long_to_look_up_does_not_stop_its_clone(
    tmp_path, url, origin, git_http, fetches
):
    """A scope stored with such a branch before PUT refused it: its refresh
    fetches nothing and reports the branch missing, and the next refresh of
    another scope on the clone fetches as before."""
    long_name = "x" * 1004
    service = _service(
        tmp_path, [_scope("s-master", url, "master"), _scope("s-long", url, long_name)]
    )
    await service.sync_scope(scope_id="s-master")
    pushed = _push(origin, "master")

    await _refresh(service, "s-long")
    await _refresh(service, "s-master")
    await service.sync_scopes(run_due_repacks=False, honor_backoff=False)

    assert _remote_heads(_clone_path(tmp_path, url))["master"] == pushed["master"]
    assert all(long_name not in str(c["refspecs"]) for c in fetches.calls)
    assert _source_id(url) not in GitPolicyFetcher.source_backoff


def test_a_branch_whose_ref_cannot_be_looked_up_is_left_out_with_one_warning(
    tmp_path, records
):
    url = "https://user:secret@git.example/repo.git"
    fetcher = GitPolicyFetcher(tmp_path, "s", _source(url, "ok"))

    class _References:
        def get(self, name):
            if name.endswith("/bad"):
                raise ValueError("reference name too long")
            return None

    class _Repo:
        references = _References()

    for _ in range(2):
        args = fetcher._narrow_fetch_args(_Repo(), frozenset({"ok", "bad"}))

    assert args == {
        "refspecs": ["+refs/heads/ok*:refs/remotes/origin/ok*"],
        "negotiation_tips": [],
    }
    (warned,) = [r for r in records if r["level"].name == "WARNING"]
    assert _source_id(url) in warned["message"]
    assert "git.example" not in warned["message"] and "secret" not in warned["message"]


@pytest.mark.asyncio
async def test_a_fetch_with_no_branch_left_to_ask_for_is_a_local_failure(
    tmp_path, url, origin, git_http, fetches, monkeypatch
):
    """Every requested branch's ref failed to look up: the fetch is not run (it
    would fetch no ref), and the sync counts a failure on this server."""
    service = await _cloned(tmp_path, url, git_http, ("master", "b1"))
    monkeypatch.setattr(
        GitPolicyFetcher,
        "_narrow_fetch_args",
        lambda self, repo, branches: {"refspecs": [], "negotiation_tips": []},
    )

    await _refresh(service, "s-b1")

    assert fetches.calls == []
    assert _source_id(url) not in GitPolicyFetcher.source_backoff


@pytest.mark.fetch_backend("libgit2")
def test_libgit2_asks_for_the_whole_refspec(tmp_path):
    fetcher = GitPolicyFetcher(tmp_path, "s", _source("https://git.example/r", "b"))
    assert fetcher._requested_branches() is None


# --- the batch ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_refreshes_during_a_fetch_share_the_next_fetch(
    tmp_path, url, origin, git_http, fetches
):
    branches = ("b1", "b2", "b3", "b4")
    service = await _cloned(tmp_path, url, git_http, ("master",) + branches)
    pushed = _push(origin, *branches)
    fetches.hold_at = 0
    first = asyncio.create_task(_refresh(service, "s-b1"))
    await asyncio.wait_for(fetches.entered.wait(), _WAIT)
    rest = [asyncio.create_task(_refresh(service, f"s-{b}")) for b in branches[1:]]
    await _until(lambda: _pending(url) == set(branches[1:]))

    fetches.release.set()
    await asyncio.wait_for(asyncio.gather(first, *rest), _WAIT)

    assert _listings(git_http) == [["refs/heads/b1"], _heads(branches[1:])]
    heads = _remote_heads(_clone_path(tmp_path, url))
    assert {b: heads[b] for b in branches} == pushed
    assert not GitPolicyFetcher.pending_branches.get(_source_id(url))


# The failures of the fetch a batch rides: whether it reached the remote, and
# how the test makes it.
_REACHED = {"refused": True, "timeout": True}
_NOT_REACHED = {
    "busy": GitCliBusyError(128, "fatal: another op holds the clone's lock"),
    "local": GitCliLocalError(128, "fatal: no space left on device"),
    "zombie-cap": GitConcurrencyLimitExceeded("too many git ops still running"),
    "cancelled": asyncio.CancelledError(),
}


def _scope_heads(clone: Path) -> Dict[str, str]:
    """Scope id -> the head its last change check told its clients."""
    repo = pygit2.Repository(str(clone))
    try:
        prefix = "refs/heads/scopes/"
        return {
            name[len(prefix) :]: str(repo.references[name].target)
            for name in repo.references
            if name.startswith(prefix)
        }
    finally:
        repo.free()


async def _behind_a_held_fetch(service, url, fetches, waiting):
    """Refresh s-master with its fetch held, then the scopes on ``waiting``,
    which join the clone's batch and wait; release the held fetch, and wait for
    every refresh to end."""
    fetches.hold_at = 0
    first = asyncio.create_task(_refresh(service, "s-master"))
    await asyncio.wait_for(fetches.entered.wait(), _WAIT)
    rest = [asyncio.create_task(_refresh(service, f"s-{b}")) for b in waiting]
    await _until(lambda: _pending(url) == set(waiting))
    fetches.release.set()
    await asyncio.wait_for(asyncio.gather(first, *rest, return_exceptions=True), _WAIT)


@pytest.mark.parametrize("cap", [1000, 0], ids=["narrow", "cap-0"])
@pytest.mark.parametrize("failure", [*_REACHED, *_NOT_REACHED])
@pytest.mark.asyncio
async def test_no_refresh_is_lost_when_the_fetch_it_rides_fails(
    failure, cap, tmp_path, url, origin, git_http, fetches, monkeypatch
):
    """The second fetch carries four refreshes' branches and fails: it counts
    only for its own sync (s-b1). One that reached the remote makes each of the
    others fetch once more when the source's backoff allows, all in one fetch;
    one that never reached it stands in for none of them, and each fetches for
    itself. Either way each of the other scopes sees its commit.

    Mutation: counting the failed fetch for every sync it carried (the
    spec's "a failed attempt counts") leaves s-b2..s-b4 on their old heads.
    """
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", cap
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_BACKOFF_BASE_SECONDS", 0.2)
    branches = ("b1", "b2", "b3", "b4")
    service = await _cloned(tmp_path, url, git_http, ("master",) + branches)
    pushed = _push(origin, *branches)
    if failure == "refused":
        fetches.refuse = {1}
    elif failure == "timeout":
        fetches.raise_at[1] = GitCliTimeoutError("git fetch exceeded its timeout")
    else:
        fetches.raise_at[1] = _NOT_REACHED[failure]

    await _behind_a_held_fetch(service, url, fetches, branches)

    heads = _scope_heads(_clone_path(tmp_path, url))
    assert {b: heads.get(f"s-{b}") for b in branches[1:]} == {
        b: pushed[b] for b in branches[1:]
    }
    if failure in _REACHED:
        assert len(fetches.calls) == 3  # held, failed, the one retry
    assert not _pending(url)


@pytest.mark.asyncio
async def test_a_sync_whose_stand_in_failed_fetches_again_when_the_backoff_allows(
    tmp_path, url, origin, git_http, fetches, monkeypatch
):
    """Not at once: the backoff the failure set governs when."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_BACKOFF_BASE_SECONDS", 0.6)
    service = await _cloned(tmp_path, url, git_http, ("master", "b1", "b2"))
    fetches.refuse = {1}

    await _behind_a_held_fetch(service, url, fetches, ("b1", "b2"))

    assert len(fetches.calls) == 3
    assert fetches.started[2] - fetches.started[1] >= 0.5


@pytest.mark.parametrize("cap", [1000, 0], ids=["narrow", "cap-0"])
@pytest.mark.asyncio
async def test_a_down_remote_costs_three_fetches_for_fifty_waiting_refreshes(
    cap, tmp_path, url, origin, git_http, fetches, monkeypatch
):
    """The fetch that runs as they arrive, the one that carries them all, and
    one more for all of them once the backoff allows; then the backoff governs.

    (0.9 fetched once per waiting refresh.)
    """
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", cap
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_BACKOFF_BASE_SECONDS", 0.5)
    names = tuple(f"w{i}" for i in range(50))
    service = _service(
        tmp_path, [_scope_on(url, "master")] + [_scope_on(url, n) for n in names]
    )
    await service.sync_scope(scope_id="s-master")
    fetches.refuse_from = 0

    await _behind_a_held_fetch(service, url, fetches, names)

    assert len(fetches.calls) == 3
    assert not _pending(url)


@pytest.mark.asyncio
async def test_a_failed_stand_in_past_the_longest_wait_is_left_to_the_backoff(
    tmp_path, url, origin, git_http, fetches, monkeypatch, records
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_BACKOFF_BASE_SECONDS", 60.0)
    monkeypatch.setattr(git_fetcher, "_FAILED_STAND_IN_MAX_WAIT_SECONDS", 30.0)
    service = await _cloned(tmp_path, url, git_http, ("master", "b1", "b2"))
    fetches.refuse = {1}

    await _behind_a_held_fetch(service, url, fetches, ("b1", "b2"))

    assert len(fetches.calls) == 2
    assert [
        r
        for r in records
        if r["message"].startswith("Not fetching") and "backed off" in r["message"]
    ]


@pytest.mark.asyncio
async def test_a_pass_s_sync_does_not_fetch_again_after_a_failed_stand_in(
    tmp_path, url, origin, git_http, fetches
):
    """A pass tries each clone once; the next pass fetches again."""
    service = await _cloned(tmp_path, url, git_http, ("master", "dev", "nb"))
    origin.branch("nb")
    fetches.refuse = {0}

    await service.sync_scopes(run_due_repacks=False, honor_backoff=False)

    assert len(fetches.calls) == 1


@pytest.mark.asyncio
async def test_a_fetch_that_never_reached_the_remote_records_nothing(
    tmp_path, url, origin, git_http, fetches
):
    service = await _cloned(tmp_path, url, git_http, ("master", "b1"))
    marks = _clone_path(tmp_path, url) / ".git" / "opal-fetched"
    before = sorted(p.name for p in marks.iterdir())
    fetches.raise_at[0] = _NOT_REACHED["busy"]

    await _refresh(service, "s-b1")

    assert not GitPolicyFetcher.branch_attempts.get(_source_id(url))
    assert sorted(p.name for p in marks.iterdir()) == before


# --- the batch holds only the syncs that wait ------------------------------------


@pytest.mark.asyncio
async def test_a_sync_that_does_not_fetch_leaves_no_branch_in_the_batch(
    tmp_path, url, origin, git_http, fetches
):
    """An unforced sync of a branch the clone has (a PUT that moves nothing), a
    hinted refresh whose commit is there: the next refresh asks only for its
    own branch."""
    origin.branch("b1")
    origin.branch("b2")
    service = await _cloned(tmp_path, url, git_http, ("master", "b1", "b2", "dev"))
    head = _remote_heads(_clone_path(tmp_path, url))["dev"]
    await service.sync_scope(scope_id="s-b2", req_time=datetime.datetime.now())
    await service.sync_scope(
        scope_id="s-dev", hinted_hash=head, req_time=datetime.datetime.now()
    )
    assert fetches.calls == []
    assert not _pending(url)

    await _refresh(service, "s-b1")

    assert _listings(git_http) == [["refs/heads/b1"]]


@pytest.mark.asyncio
async def test_a_sync_after_its_scope_was_purged_leaves_no_batch_entry(tmp_path):
    url = "https://git.example/never.git"

    async def deleted():
        return False

    fetcher = GitPolicyFetcher(
        tmp_path / "base", "s", _source(url, "b"), liveness_probe=deleted
    )
    GitPolicyFetcher.forget_fetches(_source_id(url))

    await fetcher.fetch_and_notify_on_changes(
        force_fetch=True, req_time=datetime.datetime.now()
    )

    assert not GitPolicyFetcher.pending_branches


def test_syncs_of_one_branch_leave_the_batch_one_by_one(tmp_path):
    url = "https://git.example/repo.git"
    first = GitPolicyFetcher(tmp_path, "s1", _source(url, "b"))
    second = GitPolicyFetcher(tmp_path, "s2", _source(url, "b"))

    one, two = first._join_batch(), second._join_batch()
    first._leave_batch(one)
    assert _pending(url) == {"b"}
    second._leave_batch(two)
    assert not GitPolicyFetcher.pending_branches

    taken = first._join_batch()
    first._take_batch()
    second._join_batch()
    first._leave_batch(taken)  # its batch was taken: the new one stays
    assert _pending(url) == {"b"}


# --- a sync pass ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_pass_asks_for_every_tracked_branch_in_one_fetch(
    tmp_path, url, origin, git_http, fetches
):
    branches = ("master", "dev", "feature/x", "b1")
    service = await _cloned(tmp_path, url, git_http, branches)
    pushed = _push(origin, "b1", "dev", "other")

    await service.sync_scopes(run_due_repacks=False)

    assert _listings(git_http) == [_heads(branches)]
    heads = _remote_heads(_clone_path(tmp_path, url))
    assert heads["b1"] == pushed["b1"] and heads["dev"] == pushed["dev"]
    assert "other" not in heads


@pytest.mark.asyncio
async def test_a_poll_only_pass_asks_for_the_branches_of_scopes_it_does_not_poll(
    tmp_path, url, origin, git_http, fetches
):
    """The pass's branches come from every scope, before the poll-only
    filter."""
    polled = _scope("s-polled", url, "master")
    polled.policy.poll_updates = True
    service = ScopesService(
        base_dir=tmp_path / "base",
        scopes=_Scopes([polled, _scope("s-quiet", url, "quiet")]),
        pubsub_endpoint=_PubSub(),
    )
    await service.sync_scope(scope_id="s-polled")
    git_http.bodies.clear()

    await service.sync_scopes(only_poll_updates=True, run_due_repacks=False)

    assert _listings(git_http) == [_heads({"master", "quiet"})]


@pytest.mark.asyncio
async def test_a_pass_over_the_cap_fetches_the_whole_refspec(
    tmp_path, url, origin, git_http, fetches, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", 2
    )
    service = await _cloned(tmp_path, url, git_http, ("master", "dev", "b1"))
    pushed = _push(origin, "other")
    earlier = datetime.datetime.now()
    GitPolicyFetcher.branch_attempts[_source_id(url)] = {"dev": (earlier, False)}

    await service.sync_scopes(run_due_repacks=False)

    assert _listings(git_http) == [["refs/heads/"]]
    clone = _clone_path(tmp_path, url)
    assert _remote_heads(clone)["other"] == pushed["other"]
    started = GitPolicyFetcher.repos_last_fetched[_source_id(url)].timestamp()
    assert _mark(clone, "ALL").stat().st_mtime == pytest.approx(started, abs=0.01)
    # Answered for every branch by the fetch of every branch from now on.
    assert _source_id(url) not in GitPolicyFetcher.branch_attempts


@pytest.mark.asyncio
async def test_a_cap_of_0_makes_a_refresh_fetch_the_whole_refspec(
    tmp_path, url, origin, git_http, fetches, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", 0
    )
    service = await _cloned(tmp_path, url, git_http, ("master", "b1"))
    pushed = _push(origin, "b1", "other")

    await _refresh(service, "s-b1")

    assert _listings(git_http) == [["refs/heads/"]]
    assert "refspecs" not in fetches.calls[0]
    heads = _remote_heads(_clone_path(tmp_path, url))
    assert heads["other"] == pushed["other"]


@pytest.mark.asyncio
async def test_with_a_cap_of_0_a_branch_that_cannot_be_a_ref_still_fetches(
    tmp_path, url, origin, git_http, fetches, monkeypatch
):
    """Every fetch takes the whole refspec, as before 0.10, a refresh of a
    scope whose branch no fetch can bring included."""
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", 0
    )
    service = _service(
        tmp_path, [_scope("s-master", url, "master"), _scope("s-tilde", url, "x~1")]
    )
    await service.sync_scope(scope_id="s-master")
    git_http.bodies.clear()

    await _refresh(service, "s-tilde")

    assert _listings(git_http) == [["refs/heads/"]]


@pytest.mark.asyncio
async def test_a_pass_s_fetch_takes_the_waiting_refreshes_branches(
    tmp_path, url, origin, git_http, fetches
):
    """A refresh waiting for the clone while the pass's fetch is about to start
    rides it."""
    service = await _cloned(tmp_path, url, git_http, ("master", "b1"))
    GitPolicyFetcher.pending_branches[_source_id(url)] = {"waiting": 1}

    await service.sync_scopes(run_due_repacks=False)

    assert _listings(git_http) == [_heads({"master", "b1", "waiting"})]
    assert not GitPolicyFetcher.pending_branches.get(_source_id(url))


# --- prune ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prune_removes_only_requested_branches_gone_upstream(
    tmp_path, url, origin, git_http, fetches, monkeypatch
):
    origin.branch("b1")
    origin.branch("b2")
    service = await _cloned(tmp_path, url, git_http, ("master", "b1"))
    origin.delete("b1")
    origin.delete("b2")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", True)

    await _refresh(service, "s-b1")

    heads = _remote_heads(_clone_path(tmp_path, url))
    assert "b1" not in heads
    assert {"b2", "dev", "feature/x", "master"} <= set(heads)


# --- the fetch marks --------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_marks_hold_the_fetch_start(
    tmp_path, url, origin, git_http, fetches
):
    service = await _cloned(tmp_path, url, git_http, ("master", "b1"))
    clone = _clone_path(tmp_path, url)
    cloned = GitPolicyFetcher.repos_last_fetched[_source_id(url)].timestamp()
    assert _mark(clone, "ALL").stat().st_mtime == pytest.approx(cloned, abs=0.01)
    _push(origin, "b1")

    await _refresh(service, "s-b1")

    started, succeeded = GitPolicyFetcher.branch_attempts[_source_id(url)]["b1"]
    assert succeeded is True
    assert _branch_mark(clone, "b1").stat().st_mtime == pytest.approx(
        started.timestamp(), abs=0.01
    )
    assert not _branch_mark(clone, "master").exists()
    assert not _mark(clone, "FAILED").exists()
    assert GitPolicyFetcher.repos_last_fetched[_source_id(url)].timestamp() == cloned


@pytest.mark.parametrize("cap", [1000, 0], ids=["narrow", "cap-0"])
@pytest.mark.asyncio
async def test_a_fetch_that_fails_at_the_remote_marks_what_it_asked_for(
    cap, tmp_path, url, origin, git_http, fetches, monkeypatch
):
    """A failed narrow fetch marks each branch it asked for, not the whole
    clone; a failed fetch of every branch writes FAILED."""
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", cap
    )
    service = await _cloned(tmp_path, url, git_http, ("master", "b1"))
    clone = _clone_path(tmp_path, url)
    fetches.refuse = {0}

    await _refresh(service, "s-b1")

    started, succeeded = GitPolicyFetcher.branch_attempts[_source_id(url)]["b1"]
    assert succeeded is False
    failed = _mark(clone, "FAILED") if cap == 0 else _failed_mark(clone, "b1")
    assert failed.stat().st_mtime == pytest.approx(started.timestamp(), abs=0.01)
    other = _failed_mark(clone, "b1") if cap == 0 else _mark(clone, "FAILED")
    assert not other.exists()
    assert not _branch_mark(clone, "b1").exists()
    assert _source_id(url) in GitPolicyFetcher.source_backoff


def test_a_mark_of_every_branch_takes_the_older_marks_and_dead_temp_files(
    tmp_path, monkeypatch
):
    marks = tmp_path / "opal-fetched"
    git_fetcher._write_fetch_marks(marks, ["old", "older.failed", "FAILED"], 100.0)
    git_fetcher._write_fetch_marks(marks, ["newer"], 300.0)
    (marks / ".left.0a1b2c3d").write_text("")
    monkeypatch.setattr(git_fetcher, "_FETCH_MARK_TEMP_SECONDS", 3600.0)

    git_fetcher._write_fetch_marks(marks, ["ALL"], 200.0)

    assert sorted(p.name for p in marks.iterdir()) == [".left.0a1b2c3d", "ALL", "newer"]
    monkeypatch.setattr(git_fetcher, "_FETCH_MARK_TEMP_SECONDS", -1.0)
    git_fetcher._write_fetch_marks(marks, ["ALL"], 200.0)
    assert sorted(p.name for p in marks.iterdir()) == ["ALL", "newer"]


@pytest.mark.asyncio
async def test_a_marks_write_that_fails_is_one_warning_and_the_fetch_still_counts(
    tmp_path, url, origin, git_http, fetches, records
):
    service = await _cloned(tmp_path, url, git_http, ("master", "b1"))
    marks = _clone_path(tmp_path, url) / ".git" / "opal-fetched"
    shutil.rmtree(marks)
    marks.write_text("not a directory")
    pushed = _push(origin, "b1")

    await _refresh(service, "s-b1")
    await _refresh(service, "s-b1")

    warned = [
        r
        for r in records
        if r["level"].name == "WARNING" and "Could not record" in r["message"]
    ]
    assert len(warned) == 1
    assert str(marks) in warned[0]["message"]
    assert GitPolicyFetcher.branch_attempts[_source_id(url)]["b1"][1] is True
    assert _remote_heads(_clone_path(tmp_path, url))["b1"] == pushed["b1"]
    assert _source_id(url) not in GitPolicyFetcher.source_backoff


# --- what git is given --------------------------------------------------------------


@pytest.mark.asyncio
async def test_negotiation_tips_are_the_requested_branches_existing_refs(
    tmp_path, url, origin, git_http, fetches
):
    """Git (before 2.4x) refuses a --negotiation-tip that does not resolve."""
    service = await _cloned(tmp_path, url, git_http, ("master", "dev", "nb"))
    _push(origin, "dev", "nb")

    await _refresh(service, "s-dev")
    await _refresh(service, "s-nb")

    assert [c["negotiation_tips"] for c in fetches.calls] == [
        ["refs/remotes/origin/dev"],
        [],
    ]
    assert [c["refspecs"] for c in fetches.calls] == [
        ["+refs/heads/dev*:refs/remotes/origin/dev*"],
        ["+refs/heads/nb*:refs/remotes/origin/nb*"],
    ]


@pytest.mark.asyncio
async def test_cli_fetch_gives_git_the_refspecs_and_tips_it_is_given(
    tmp_path, git_origin, monkeypatch
):
    clone = tmp_path / "clone"
    source = _source(git_origin.url, "master")
    await git_cli.cli_clone(git_origin.url, clone, source, remote="origin", timeout=30)
    master = git_origin.commit("master")
    dev = git_origin.commit("dev")
    seen: List[List[str]] = []
    real = git_cli._run_git

    async def spy(args, **kwargs):
        seen.append(list(args))
        return await real(args, **kwargs)

    monkeypatch.setattr(git_cli, "_run_git", spy)

    await cli_fetch(
        clone,
        "origin",
        source,
        prune=False,
        timeout=30,
        refspecs=["+refs/heads/master*:refs/remotes/origin/master*"],
        negotiation_tips=["refs/remotes/origin/master"],
    )

    (args,) = seen
    end = args.index("--")
    assert "--negotiation-tip=refs/remotes/origin/master" in args[:end]
    assert args[end + 2 :] == ["+refs/heads/master*:refs/remotes/origin/master*"]
    heads = _remote_heads(clone)
    assert heads["master"] == master
    assert heads["dev"] != dev


@pytest.mark.asyncio
async def test_cli_fetch_refuses_an_empty_refspec_list(tmp_path, git_origin):
    with pytest.raises(ValueError, match="no refspec"):
        await cli_fetch(
            tmp_path,
            "origin",
            _source(git_origin.url, "master"),
            prune=False,
            timeout=30,
            refspecs=[],
        )


# --- libgit2 ------------------------------------------------------------------------


@pytest.mark.fetch_backend("libgit2")
@pytest.mark.asyncio
async def test_libgit2_fetches_are_not_narrowed(tmp_path, url, origin, git_http):
    service = await _cloned(tmp_path, url, git_http, ("master", "b1"))
    pushed = _push(origin, "b1", "b2")

    await _refresh(service, "s-b1")

    clone = _clone_path(tmp_path, url)
    heads = _remote_heads(clone)
    assert heads["b1"] == pushed["b1"] and heads["b2"] == pushed["b2"]
    assert not (clone / ".git" / "opal-fetched").exists()
    assert not GitPolicyFetcher.pending_branches
    assert not GitPolicyFetcher.branch_attempts


# --- the setting, and forgetting a source ---------------------------------------------


@pytest.mark.parametrize("backend, refused", [("cli", True), ("libgit2", False)])
def test_a_negative_cap_stops_the_server_with_the_cli(backend, refused, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", backend == "cli"
    )
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES", -1
    )
    if not refused:
        validate_git_cli_settings()
        return
    with pytest.raises(ValueError, match="SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES=-1"):
        validate_git_cli_settings()


def test_the_cap_defaults_to_1000():
    assert opal_server_config.SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES == 1000


def test_a_purge_and_reset_caches_forget_the_batch_and_the_attempts(tmp_path):
    now = datetime.datetime.now()
    for forget in (
        lambda: purge_local_memory("src-0", str(tmp_path / "src-0")),
        GitPolicyFetcher.reset_caches,
    ):
        GitPolicyFetcher.pending_branches["src-0"] = {"b": 1}
        GitPolicyFetcher.branch_attempts["src-0"] = {"b": (now, False)}

        forget()

        assert "src-0" not in GitPolicyFetcher.pending_branches
        assert "src-0" not in GitPolicyFetcher.branch_attempts


def test_fetched_after_reads_the_branch_s_last_attempt(tmp_path):
    url = "https://git.example/repo.git"
    fetcher = GitPolicyFetcher(tmp_path, "s", _source(url, "b"))
    t = datetime.datetime.now()
    later = t + datetime.timedelta(seconds=1)
    earlier = t - datetime.timedelta(seconds=1)
    source_id = _source_id(url)

    assert fetcher._fetched_after("b", t) is None
    GitPolicyFetcher.branch_attempts[source_id] = {"b": (later, False)}
    assert fetcher._fetched_after("b", t) is False
    assert fetcher._fetched_after("other", t) is None
    GitPolicyFetcher.branch_attempts[source_id] = {"b": (later, True)}
    assert fetcher._fetched_after("b", t) is True
    GitPolicyFetcher.branch_attempts[source_id] = {"b": (earlier, True)}
    assert fetcher._fetched_after("b", t) is None
    GitPolicyFetcher.branch_attempts[source_id] = {"b": (t, True)}
    assert fetcher._fetched_after("b", t) is None
    GitPolicyFetcher.repos_last_fetched[source_id] = later
    assert fetcher._fetched_after("other", t) is True
    GitPolicyFetcher.repos_last_fetched[source_id] = t
    assert fetcher._fetched_after("other", t) is None
