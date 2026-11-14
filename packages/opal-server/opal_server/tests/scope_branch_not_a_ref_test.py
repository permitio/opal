"""A scope whose branch cannot name a git ref (an empty one, ``x~1``) does not
stop the fetch of its clone, and PUT /scopes refuses such a branch.

A sync pass fetches each clone once, in phase 1, through the first scope
it lists on it; the clone's other scopes, in phase 2, read what that
fetch brought. When that first scope's branch could not be a ref, the
check of the clone's remote-tracking ref for it raised InvalidSpecError
before the fetch, so the clone was not fetched in the pass and its other
scopes kept serving what they had. The check now takes such a branch for
one the clone does not have, as it takes a missing branch, and the pass
goes on to the fetch. So do the lookups of the branch after the fetch,
and in a phase-2 sync of a scope on it: such a scope reports a missing
branch, and the fetch made through it marks the clone for its repack.

No fetch can bring such a branch, so PUT /scopes answers 422 for one and
stores nothing. A scope stored with one before that check existed is not
served the commit the name would resolve to as a revision (``x~1``, the
parent of ``origin/x``): a scope's branch is looked up by its exact ref
name, so such a scope reports a missing branch, is never notified, and its
bundle requests get the 409 of a branch that does not exist. The same
lookup keeps a tag named like the remote-tracking branch (``origin/main``)
from standing in for it.

Each test runs with libgit2 and with the git command line
(SCOPES_GIT_FETCH_WITH_CLI).
"""

from pathlib import Path

import git
import pygit2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opal_common.schemas.policy_source import (
    BasePolicyScopeSource,
    GitPolicyScopeSource,
    NoAuthData,
)
from opal_common.schemas.scopes import Scope
from opal_common.tests.log_capture import capture_records
from opal_server import git_fetcher
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.api import init_scope_router, verify_branch_or_throw
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService

_AUTHOR = git.Actor("test", "test@example.com")
# The last: its refs/remotes/origin/ ref is 1,024 bytes, which libgit2 refuses
# to look up.
_BRANCHES_THAT_CANNOT_BE_REFS = ["", "x~1", "b" * 1004]


class _Scopes:
    def __init__(self, scopes):
        self.scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self.scopes:
            raise ScopeNotFoundError(scope_id)
        return self.scopes[scope_id]

    async def all(self):
        return list(self.scopes.values())

    async def put(self, scope):
        self.scopes[scope.scope_id] = scope


class _PubSub:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        topics = [topics] if isinstance(topics, str) else list(topics)
        self.published.append((topics, data))

    def notified_scopes(self):
        return {
            topic.split(":", 1)[0] for topics, _ in self.published for topic in topics
        }


class _Authenticator:
    enabled = False

    def __call__(self):
        return {}


pytestmark = pytest.mark.fetch_backend("both")


@pytest.fixture(autouse=True)
def _clean_fetcher_state(monkeypatch):
    # One clone per URL whatever the environment says, and no repack at the
    # end of a pass.
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", 0)
    monkeypatch.setattr(git_fetcher, "_repacks_due", {})
    monkeypatch.setattr(git_fetcher, "_sync_passes_in_flight", 0)
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    yield
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()


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


def _scope(scope_id: str, url: str, branch: str = "main") -> Scope:
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git", url=url, branch=branch, auth=NoAuthData()
        ),
    )


def _remote_tracking_head(base_dir: Path, scope: Scope) -> str:
    clone = pygit2.Repository(
        str(GitPolicyFetcher.repo_clone_path(base_dir, scope.policy))
    )
    try:
        return str(clone.lookup_reference("refs/remotes/origin/main").target)
    finally:
        clone.free()


@pytest.mark.asyncio
@pytest.mark.parametrize("branch", _BRANCHES_THAT_CANNOT_BE_REFS)
async def test_a_branch_that_cannot_be_a_ref_does_not_stop_the_fetch_of_its_clone(
    tmp_path, branch
):
    """The scope on such a branch is listed first, so phase 1 syncs the clone
    through it; its sibling on main must see the commit pushed since the last
    sync.

    Mutation: without the InvalidSpecError at the lookup in
    _get_valid_repo, the clone is not fetched and main stays behind.
    """
    origin = _origin(tmp_path / "origin")
    url = origin.working_tree_dir
    bad, sibling = _scope("s-bad", url, branch), _scope("s-sibling", url)
    base_dir = tmp_path / "opal"
    pubsub = _PubSub()
    svc = ScopesService(
        base_dir=base_dir, scopes=_Scopes([bad, sibling]), pubsub_endpoint=pubsub
    )
    await svc.sync_scope(scope_id="s-sibling")
    _commit(origin, "policy/b.rego", "package b\n")
    pubsub.published.clear()

    await svc.sync_scopes()

    assert _remote_tracking_head(base_dir, sibling) == origin.head.commit.hexsha
    assert "s-sibling" in pubsub.notified_scopes()


@pytest.mark.asyncio
@pytest.mark.parametrize("branch", _BRANCHES_THAT_CANNOT_BE_REFS)
async def test_scopes_on_a_branch_that_cannot_be_a_ref_report_it_missing(
    tmp_path, monkeypatch, branch
):
    """Two scopes on such a branch: the first listed, through which phase 1
    fetches the clone, and one synced in phase 2. The fetch marks the clone
    due for its repack, and the pass logs one missing-branch line for the
    branch and no failed sync.

    Mutation: InvalidSpecError raised by RepoInterface.has_remote_branch
    fails the phase-2 sync, and raised by RepoInterface.get_commit_hash the
    phase-1 sync of an empty branch.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", 2)
    origin = _origin(tmp_path / "origin")
    url = origin.working_tree_dir
    sibling = _scope("s-sibling", url)
    scopes = _Scopes(
        [_scope("s-bad", url, branch), sibling, _scope("s-bad-2", url, branch)]
    )
    svc = ScopesService(
        base_dir=tmp_path / "opal", scopes=scopes, pubsub_endpoint=_PubSub()
    )
    await svc.sync_scope(scope_id="s-sibling")
    # A pack of a fetch before the pass's, so that the pass's fetch takes a
    # git clone (refs packed by git) to the pack limit; a libgit2 clone,
    # its refs each in a file of their own, is marked below the limit.
    _commit(origin, "policy/b.rego", "package b\n")
    await svc.sync_scope(scope_id="s-sibling", force_fetch=True)
    _commit(origin, "policy/c.rego", "package c\n")
    git_fetcher._repacks_due.clear()

    with capture_records() as logs:
        await svc.sync_scopes(run_due_repacks=False)

    assert set(git_fetcher._repacks_due) == {GitPolicyFetcher.source_id(sibling.policy)}
    assert [r["message"] for r in logs.emitted if r["level"].name == "ERROR"] == [
        f"Did not find target branch on remote: {branch} ({url})"
    ]


def _client(store: _Scopes, pubsub: _PubSub, base_dir: Path) -> TestClient:
    service = ScopesService(base_dir=base_dir, scopes=store, pubsub_endpoint=pubsub)
    app = FastAPI()
    app.include_router(
        init_scope_router(store, _Authenticator(), pubsub, service),
        prefix="/scopes",
    )
    return TestClient(app)


@pytest.mark.parametrize("branch", _BRANCHES_THAT_CANNOT_BE_REFS)
def test_put_scope_refuses_a_branch_that_cannot_be_a_ref(tmp_path, monkeypatch, branch):
    """For a new scope and for an update of a stored one: 422, the stored
    record is unchanged and no sync is asked for."""
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    url = "https://git.example.com/org/policy.git"
    stored = _scope("s-stored", url)
    store = _Scopes([stored])
    pubsub = _PubSub()
    client = _client(store, pubsub, tmp_path)

    for scope_id in ("s-new", "s-stored"):
        response = client.put(
            "/scopes", json=_scope(scope_id, url, branch).model_dump()
        )

        assert response.status_code == 422, response.text
        assert response.json() == {
            "detail": {"error": f"policy.branch {branch!r} cannot be a git branch name"}
        }
    assert store.scopes == {"s-stored": stored}
    assert pubsub.published == []


def test_put_scope_takes_a_branch_with_a_slash(tmp_path, monkeypatch):
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    store = _Scopes([])
    scope = _scope("s1", "https://git.example.com/org/policy.git", "release/v1.2")

    response = _client(store, _PubSub(), tmp_path).put(
        "/scopes", json=scope.model_dump()
    )

    assert response.status_code == 201, response.text
    assert store.scopes == {"s1": scope}


def test_put_scope_takes_a_branch_of_1003_characters(tmp_path, monkeypatch):
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    store = _Scopes([])
    scope = _scope("s1", "https://git.example.com/org/policy.git", "b" * 1003)

    response = _client(store, _PubSub(), tmp_path).put(
        "/scopes", json=scope.model_dump()
    )

    assert response.status_code == 201, response.text


def test_the_branch_check_passes_a_policy_that_is_not_on_git():
    """The check is for git sources only. Scope.policy admits only
    GitPolicyScopeSource today, and its source_type is free-form, so no PUT
    /scopes body carries another source; model_construct builds a scope on the
    base source type, as one of a later non-git type would be.

    Mutation: making the non-git early return in verify_branch_or_throw
    raise, or dropping it, fails here.
    """
    policy = BasePolicyScopeSource(
        source_type="bundle", url="https://bundles.example.com/p", auth=NoAuthData()
    )
    scope = Scope.model_construct(
        scope_id="s-other", policy=policy, data={"entries": []}
    )

    assert verify_branch_or_throw(scope) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("hinted_hash", ["a..b", "^{tree}"])
async def test_a_hinted_hash_that_cannot_be_parsed_counts_as_unknown(
    tmp_path, hinted_hash
):
    """A refresh's hinted_hash comes from whoever calls the refresh. One that
    is no revision git can parse is taken for a hash the clone does not
    have: the clone is fetched, as for an unknown one, not failed.

    Mutation: catching KeyError alone around revparse_single in
    _should_fetch lets InvalidSpecError out of the sync, and fails here.
    """
    origin = _origin(tmp_path / "origin")
    url = origin.working_tree_dir
    scope = _scope("s1", url)
    base_dir = tmp_path / "opal"
    pubsub = _PubSub()
    svc = ScopesService(
        base_dir=base_dir, scopes=_Scopes([scope]), pubsub_endpoint=pubsub
    )
    await svc.sync_scope(scope_id="s1")
    _commit(origin, "policy/b.rego", "package b\n")

    await svc.sync_scope(scope_id="s1", hinted_hash=hinted_hash)

    assert _remote_tracking_head(base_dir, scope) == origin.head.commit.hexsha


def _origin_with_branch_x(path: Path) -> git.Repo:
    """An origin with main and a branch x two commits ahead of it, so that
    ``x~1`` read as a revision names a commit: the first of the two."""
    repo = _origin(path)
    repo.git.checkout("-b", "x")
    _commit(repo, "policy/x1.rego", "package x1\n")
    _commit(repo, "policy/x2.rego", "package x2\n")
    repo.git.checkout("main")
    return repo


@pytest.mark.asyncio
async def test_a_stored_scope_on_a_revision_of_a_branch_is_not_served_that_commit(
    tmp_path, monkeypatch
):
    """A scope stored (before PUT refused such names) with the branch ``x~1``:
    a pass reports its branch missing once and notifies only its sibling on x,
    the scope stays stored, and its bundle request gets the 409 at once.

    Mutation: resolving the branch as a revision (resolve_refish) in
    RepoInterface.get_commit_hash notifies the scope; in
    _get_current_branch_head it serves the parent of origin/x (200).
    """
    origin = _origin_with_branch_x(tmp_path / "origin")
    url = origin.working_tree_dir
    base_dir = tmp_path / "opal"
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(base_dir))
    bad, sibling = _scope("s-bad", url, "x~1"), _scope("s-x", url, "x")
    store = _Scopes([bad, sibling])
    pubsub = _PubSub()
    svc = ScopesService(base_dir=base_dir, scopes=store, pubsub_endpoint=pubsub)

    with capture_records() as logs:
        await svc.sync_scopes()

    assert [r["message"] for r in logs.emitted if r["level"].name == "ERROR"] == [
        f"Did not find target branch on remote: x~1 ({url})"
    ]
    assert pubsub.notified_scopes() == {"s-x"}
    assert set(store.scopes) == {"s-bad", "s-x"}
    response = _client(store, pubsub, base_dir).get("/scopes/s-bad/policy")
    assert response.status_code == 409, response.text
    served = _client(store, pubsub, base_dir).get("/scopes/s-x/policy")
    assert served.status_code == 200, served.text
    assert served.json()["hash"] == origin.heads.x.commit.hexsha


def _tag_in_clone(base_dir: Path, scope: Scope, name: str, target: str) -> None:
    """A tag in the scope's clone, as a fetch that follows tags brings one from
    the remote."""
    clone = pygit2.Repository(
        str(GitPolicyFetcher.repo_clone_path(base_dir, scope.policy))
    )
    try:
        clone.create_reference(f"refs/tags/{name}", pygit2.Oid(hex=target))
    finally:
        clone.free()


@pytest.mark.asyncio
async def test_a_tag_named_like_the_remote_branch_does_not_stand_in_for_it(
    tmp_path, monkeypatch
):
    """A tag ``origin/main`` at an old commit, beside refs/remotes/origin/main:
    the sync notifies the branch's new head, moves the scope's local branch
    there, and the bundle is built at the branch head, not at the tag.

    Mutation: resolving ``origin/main`` by its short name (resolve_refish,
    where refs/tags/ comes before refs/remotes/) in get_commit_hash or in
    _get_current_branch_head picks the tag.
    """
    origin = _origin(tmp_path / "origin")
    old = origin.head.commit.hexsha
    url = origin.working_tree_dir
    base_dir = tmp_path / "opal"
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(base_dir))
    scope = _scope("s1", url)
    store = _Scopes([scope])
    pubsub = _PubSub()
    svc = ScopesService(base_dir=base_dir, scopes=store, pubsub_endpoint=pubsub)
    await svc.sync_scope(scope_id="s1")
    _tag_in_clone(base_dir, scope, "origin/main", old)
    _commit(origin, "policy/b.rego", "package b\n")
    new = origin.head.commit.hexsha
    pubsub.published.clear()

    await svc.sync_scope(scope_id="s1", force_fetch=True)

    assert _remote_tracking_head(base_dir, scope) == new
    assert "s1" in pubsub.notified_scopes()
    clone = pygit2.Repository(
        str(GitPolicyFetcher.repo_clone_path(base_dir, scope.policy))
    )
    try:
        local = clone.lookup_reference("refs/heads/scopes/s1")
        assert str(local.target) == new
    finally:
        clone.free()
    response = _client(store, pubsub, base_dir).get("/scopes/s1/policy")
    assert response.status_code == 200, response.text
    assert response.json()["hash"] == new


def _on_another_shard(branches, taken: str, url: str, shards: int) -> str:
    """The first of ``branches`` whose libgit2 clone (of ``shards``) is not the
    clone of the branch ``taken``."""
    taken_id = GitPolicyFetcher.source_id(_scope("t", url, taken).policy)
    for branch in branches:
        if GitPolicyFetcher.source_id(_scope("b", url, branch).policy) != taken_id:
            return branch
    raise AssertionError(f"no branch of {branches} off {taken}'s shard of {shards}")


@pytest.mark.asyncio
@pytest.mark.fetch_backend("libgit2")
async def test_with_libgit2_shards_a_revision_branch_gets_409_before_its_clone(
    tmp_path, monkeypatch
):
    """libgit2 with 3 clones per repository: a scope stored with a branch
    that cannot be a ref hashes to a shard no other scope uses, whose clone
    does not exist until a sync makes one. Its bundle requests get the 409
    at once, before that clone and after it; a valid branch on a shard with
    no clone yet still gets the 503 of a clone not there.

    Mutation: building the bundle without the ref-name check first answers
    503 (no such path) until a sync clones the shard.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    origin = _origin_with_branch_x(tmp_path / "origin")
    url = origin.working_tree_dir
    base_dir = tmp_path / "opal"
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(base_dir))
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 0)
    bad_branch = _on_another_shard([f"x~{n}" for n in range(1, 40)], "x", url, 3)
    unsynced = _on_another_shard([f"b{n}" for n in range(40)], "x", url, 3)
    bad = _scope("s-bad", url, bad_branch)
    sibling = _scope("s-x", url, "x")
    store = _Scopes([sibling, bad, _scope("s-new", url, unsynced)])
    pubsub = _PubSub()
    svc = ScopesService(base_dir=base_dir, scopes=store, pubsub_endpoint=pubsub)
    await svc.sync_scope(scope_id="s-x")
    client = _client(store, pubsub, base_dir)
    bad_clone = GitPolicyFetcher.repo_clone_path(base_dir, bad.policy)
    assert not bad_clone.exists()

    before = client.get("/scopes/s-bad/policy")
    assert client.get("/scopes/s-new/policy").status_code == 503
    await svc.sync_scopes()
    after = client.get("/scopes/s-bad/policy")

    assert (before.status_code, after.status_code) == (409, 409), before.text
    assert set(store.scopes) == {"s-bad", "s-x", "s-new"}


@pytest.mark.asyncio
@pytest.mark.fetch_backend("libgit2")
async def test_with_libgit2_shards_a_tag_named_like_the_branch_does_not_stand_in(
    tmp_path, monkeypatch
):
    """The tag case of test_a_tag_named_like_the_remote_branch_does_not_stand_in_for_it,
    with 3 clones per repository: the branch's own shard's clone serves the
    branch head."""
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    origin = _origin(tmp_path / "origin")
    old = origin.head.commit.hexsha
    url = origin.working_tree_dir
    base_dir = tmp_path / "opal"
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(base_dir))
    scope = _scope("s1", url)
    store = _Scopes([scope])
    pubsub = _PubSub()
    svc = ScopesService(base_dir=base_dir, scopes=store, pubsub_endpoint=pubsub)
    await svc.sync_scope(scope_id="s1")
    _tag_in_clone(base_dir, scope, "origin/main", old)
    _commit(origin, "policy/b.rego", "package b\n")
    new = origin.head.commit.hexsha

    await svc.sync_scope(scope_id="s1", force_fetch=True)

    assert _remote_tracking_head(base_dir, scope) == new
    response = _client(store, pubsub, base_dir).get("/scopes/s1/policy")
    assert response.status_code == 200, response.text
    assert response.json()["hash"] == new
