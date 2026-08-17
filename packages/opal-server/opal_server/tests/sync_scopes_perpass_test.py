"""sync_scopes runs its two passes, each bounded by SCOPES_GIT_MAX_WORKERS.

Phase 1 (distinct repos, network clone/fetch) and phase 2 (scopes
reusing an already-handled repo, local change-check only) are both
capped at SCOPES_GIT_MAX_WORKERS. Phase 2 shares the loop's default
executor with policy-bundle serving, so it must honor the same knob
rather than a hard-coded floor (the earlier max(MAX_WORKERS, 32) made 32
a floor the knob could not lower and over-subscribed that pool).
"""
import asyncio

import pytest
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        await asyncio.sleep(0)
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        await asyncio.sleep(0)
        return list(self._scopes.values())

    async def delete(self, scope_id):
        await asyncio.sleep(0)
        self._scopes.pop(scope_id, None)


class FakePubSubEndpoint:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append((list(topics), data))


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
async def test_both_passes_bounded_by_the_git_worker_knob(tmp_path, monkeypatch):
    # Phase 2 must honor SCOPES_GIT_MAX_WORKERS, not a hard floor: with the knob
    # at 2, phase 2 (6 duplicate scopes) must peak at <= 2, not 6. The old
    # max(MAX_WORKERS, 32) floor would let all 6 run at once (peak=6).
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 2)

    # 6 distinct repos, 2 scopes each -> 6 unique (phase 1), 6 duplicates (phase 2).
    scopes = []
    for r in range(6):
        scopes.append(_scope(f"s{r}a", f"https://git/r{r}.git"))
        scopes.append(_scope(f"s{r}b", f"https://git/r{r}.git"))

    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository(scopes),
        pubsub_endpoint=FakePubSubEndpoint(),
    )

    in_flight = {True: 0, False: 0}
    peak = {True: 0, False: 0}

    # Keyword-only and exhaustive on purpose: this double is what pins the
    # call shape _sync_one uses, so a parameter silently dropped there (e.g.
    # honor_backoff, which decides whether the pass skips a failing source)
    # reddens here instead of shipping.
    async def fake_sync_scope(
        *, scope_id, force_fetch, notify_on_changes, honor_backoff
    ):
        assert honor_backoff is True, "a periodic pass must honour the backoff"
        in_flight[force_fetch] += 1
        peak[force_fetch] = max(peak[force_fetch], in_flight[force_fetch])
        await asyncio.sleep(0.02)
        in_flight[force_fetch] -= 1

    monkeypatch.setattr(svc, "sync_scope", fake_sync_scope)

    await svc.sync_scopes()

    # Phase 1 = force_fetch=True (network); phase 2 = force_fetch=False (local).
    assert peak[True] <= 2, f"phase 1 exceeded the git cap: peak={peak[True]}"
    assert (
        peak[False] <= 2
    ), f"phase 2 exceeded SCOPES_GIT_MAX_WORKERS (is the max(,32) floor back?): peak={peak[False]}"
    assert (
        peak[False] > 1
    ), f"phase 2 ran serially, not concurrently: peak={peak[False]}"


@pytest.mark.asyncio
async def test_git_pass_still_respects_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_MAX_WORKERS", 3)

    # 9 distinct repos -> all unique, all go through phase 1 (network cap).
    scopes = [_scope(f"s{i}", f"https://git/r{i}.git") for i in range(9)]
    svc = ScopesService(
        base_dir=tmp_path,
        scopes=FakeScopeRepository(scopes),
        pubsub_endpoint=FakePubSubEndpoint(),
    )

    in_flight = 0
    peak = 0

    async def fake_sync_scope(
        *, scope_id, force_fetch, notify_on_changes, honor_backoff
    ):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1

    monkeypatch.setattr(svc, "sync_scope", fake_sync_scope)

    await svc.sync_scopes()

    assert peak <= 3, f"phase 1 exceeded the git cap: peak={peak}"
    assert peak > 1, "phase 1 did not run in parallel at all"
