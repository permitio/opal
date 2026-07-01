import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        return list(self._scopes.values())

    async def delete(self, scope_id):
        self._scopes.pop(scope_id, None)


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


@pytest.mark.asyncio
async def test_delete_unique_scope_purges_caches(tmp_path, monkeypatch):
    scope = _scope("only", "https://git/repo-a.git")
    repo = FakeScopeRepository([scope])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    src = scope.policy
    sid = GitPolicyFetcher.source_id(src)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, src))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"

    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree", lambda *a, **k: None
    )

    await svc.delete_scope("only")

    assert clone_path not in GitPolicyFetcher.repos
    assert sid not in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_delete_keeps_caches_when_sibling_shares_source(tmp_path, monkeypatch):
    a = _scope("a", "https://git/shared.git")
    b = _scope("b", "https://git/shared.git")  # same url+branch -> same source_id
    repo = FakeScopeRepository([a, b])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    sid = GitPolicyFetcher.source_id(a.policy)
    clone_path = str(GitPolicyFetcher.repo_clone_path(tmp_path, a.policy))
    GitPolicyFetcher.repos[clone_path] = object()
    GitPolicyFetcher.repos_last_fetched[sid] = "ts"

    rmtree_calls = []
    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree",
        lambda p, **k: rmtree_calls.append(p),
    )

    await svc.delete_scope("a")

    assert rmtree_calls == []  # sibling shares the source id; clone must survive
    assert clone_path in GitPolicyFetcher.repos
    assert sid in GitPolicyFetcher.repos_last_fetched


@pytest.mark.asyncio
async def test_delete_purges_when_sibling_shares_url_but_not_source(
    tmp_path, monkeypatch
):
    """Same url, different branch, sharded clones (SCOPES_REPO_CLONES_SHARDS>1)
    resolve to different source_ids -> different clone dirs.

    Deleting one must still purge its own clone + caches; the url-
    sharing sibling lives elsewhere.
    """
    # shards=4: branch "main" -> index 1, "dev" -> index 3 (distinct source_ids).
    monkeypatch.setattr(
        "opal_server.git_fetcher.opal_server_config.SCOPES_REPO_CLONES_SHARDS", 4
    )
    a = _scope("a", "https://git/shared.git", branch="main")
    b = _scope("b", "https://git/shared.git", branch="dev")  # same url, diff source_id
    assert GitPolicyFetcher.source_id(a.policy) != GitPolicyFetcher.source_id(b.policy)

    repo = FakeScopeRepository([a, b])
    svc = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)

    sid_a = GitPolicyFetcher.source_id(a.policy)
    clone_path_a = str(GitPolicyFetcher.repo_clone_path(tmp_path, a.policy))
    GitPolicyFetcher.repos[clone_path_a] = object()
    GitPolicyFetcher.repos_last_fetched[sid_a] = "ts"

    rmtree_calls = []
    monkeypatch.setattr(
        "opal_server.scopes.service.shutil.rmtree",
        lambda p, **k: rmtree_calls.append(str(p)),
    )

    await svc.delete_scope("a")

    assert rmtree_calls == [clone_path_a]  # its own clone dir removed
    assert clone_path_a not in GitPolicyFetcher.repos
    assert sid_a not in GitPolicyFetcher.repos_last_fetched
