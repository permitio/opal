"""A scope whose branch cannot name a git ref (an empty one, ``x~1``) does not
stop the fetch of its clone, and PUT /scopes refuses such a branch (PER-17994).

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
stores nothing.

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
_BRANCHES_THAT_CANNOT_BE_REFS = ["", "x~1"]


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


@pytest.fixture(autouse=True, params=["libgit2", "cli"])
def _backend(request, monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", request.param == "cli"
    )


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
