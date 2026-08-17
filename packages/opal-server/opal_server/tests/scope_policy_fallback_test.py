"""GET /scopes/{scope_id}/policy when the clone dir vanishes.

Record missing -> default scope bundle (unchanged contract). Record
PRESENT but the clone is transiently broken -> 503 + Retry-After: a live
tenant must never be served another tenant's policy (PR3 flip of the
PR2-era regression lock).
"""

import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from git import NoSuchPathError
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.api import init_scope_router
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


class FakeAuthenticator:
    """Mimics a JWTAuthenticator whose verifier is disabled (no public key)."""

    enabled = False

    def __call__(self):
        return {}


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


def _client(repo, base_dir):
    service = ScopesService(base_dir=base_dir, scopes=repo, pubsub_endpoint=None)
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), None, service),
        prefix="/scopes",
    )
    return TestClient(app)


def _default_bundle():
    return PolicyBundle(
        manifest=[], hash="default-head", data_modules=[], policy_modules=[]
    )


def test_live_scope_clone_vanish_returns_retryable_503(tmp_path, monkeypatch):
    live = _scope("live", "https://git/live.git")
    default = _scope("default", "https://git/default.git")
    repo = FakeScopeRepository([live, default])

    def fake_make_bundle(self, base_hash):
        if self._scope_id == "live":
            raise NoSuchPathError(str(tmp_path / "gone"))
        return _default_bundle()

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake_make_bundle)
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    resp = _client(repo, tmp_path).get("/scopes/live/policy")

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "5"


def test_live_scope_oserror_returns_retryable_503(tmp_path, monkeypatch):
    """make_bundle's tree-walk can raise raw OSError if the dir vanishes mid-
    walk — an unhandled 500 before PR3."""
    live = _scope("live", "https://git/live.git")
    repo = FakeScopeRepository([live])

    def fake_make_bundle(self, base_hash):
        raise OSError(2, "No such file or directory")

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake_make_bundle)
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    resp = _client(repo, tmp_path).get("/scopes/live/policy")

    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "5"


def test_missing_scope_still_falls_back_to_default_bundle(tmp_path, monkeypatch):
    """Pre-existing behaviour, pinned as CHARACTERIZATION — not endorsed.

    A missing record serves the `default` scope's policy modules at HTTP 200,
    while `_allowed_scoped_authenticator` authorized the caller for `scope_id`
    only and says nothing about "default". A PDP holding
    `allowed_scopes: ["acme"]` therefore loads another tenant's bundle into OPA
    whenever `acme` is deleted or the store briefly raises ScopeNotFoundError —
    no 4xx, no alert.

    That is the same cross-tenant hand-off the 503 introduced below exists to
    prevent ("Serving the default scope's bundle here would hand a live tenant
    another tenant's policy"), and it is inconsistent with `get_scope` and
    `refresh_scope`, which 404 the identical condition. It is left unchanged
    here only to keep PR3 scoped to the git-resilience work; the fix (404, or
    gating the fallback on the caller being authorized for "default") needs its
    own compatibility discussion, recorded on PER-15157.

    So this pins WHAT HAPPENS TODAY, so a change is deliberate — it does not
    say the behaviour is right.
    """
    default = _scope("default", "https://git/default.git")
    repo = FakeScopeRepository([default])

    monkeypatch.setattr(
        GitPolicyFetcher, "make_bundle", lambda self, base_hash: _default_bundle()
    )
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    resp = _client(repo, tmp_path).get("/scopes/ghost/policy")

    assert resp.status_code == 200
    assert resp.json()["hash"] == "default-head"


from opal_server.git_fetcher import BranchHeadNotFoundError


def test_wrong_branch_returns_non_retryable_409(tmp_path, monkeypatch):
    """Deliberately runs with the clone wait at its DEFAULT, unlike the two
    tests below that pin it at 0.

    BranchHeadNotFoundError and CloneNotPopulatedError are both
    ValueError subclasses, so widening the exception the wait catches by
    a single level would swallow this permanent misconfiguration into a
    20s hold — still a 409, just twenty seconds late, on every poll of
    every affected PDP. The wall-clock assertion is what makes that
    visible here.
    """
    live = _scope("live", "https://git/live.git", branch="does-not-exist")
    repo = FakeScopeRepository([live])

    def fake_make_bundle(self, base_hash):
        raise BranchHeadNotFoundError("Could not find current branch head")

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake_make_bundle)
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    started = time.monotonic()
    resp = _client(repo, tmp_path).get("/scopes/live/policy")
    elapsed = time.monotonic() - started
    assert resp.status_code == 409
    assert "retry-after" not in resp.headers
    assert elapsed < 5.0, (
        f"a permanent misconfiguration was held for {elapsed:.1f}s by the "
        "clone wait, which only an unpopulated clone should enter"
    )


# --- F17/F7: _get_current_branch_head must distinguish a PERMANENT missing
# branch (KeyError -> BranchHeadNotFoundError -> 409) from a TRANSIENT object-
# store failure (pygit2.GitError -> propagates -> retryable 503). Previously
# RepoInterface.get_commit_hash collapsed both to None, so a self-healing scope
# got a non-retryable 409. These exercise the REAL method (not a mock of
# make_bundle) so the raise path is actually covered. ---
import pygit2  # noqa: E402
from opal_server.git_fetcher import GitPolicyFetcher as _Fetcher  # noqa: E402


class _FakeRepo:
    """Stand-in for pygit2.Repository whose resolve_refish outcome we control.

    ``refs`` is the on-disk reference list. It decides the KeyError split: an
    empty remote-tracking namespace means the clone is still being populated
    (transient), refs present but not ours means the branch is misconfigured
    (permanent). Defaults to a populated namespace so existing callers keep
    exercising the permanent case.
    """

    def __init__(self, resolve, refs=("refs/remotes/origin/some-other-branch",)):
        self._resolve = resolve
        self._refs = list(refs)

    def resolve_refish(self, refish):
        return self._resolve()

    def listall_references(self):
        return self._refs

    def free(self):  # _get_current_branch_head free()s the handle in finally
        pass


class _FakeCommit:
    def __init__(self, hex_):
        self.hex = hex_


def _raise(exc):
    def _f():
        raise exc

    return _f


def _branch_head_fetcher(tmp_path, branch="main"):
    src = GitPolicyScopeSource(
        source_type="git",
        url="https://git/live.git",
        branch=branch,
        auth=NoAuthData(auth_type="none"),
    )
    return _Fetcher(tmp_path, "s1", src)


def test_branch_head_missing_ref_is_permanent_branchheadnotfound(tmp_path, monkeypatch):
    # resolve_refish raises KeyError AND the remote namespace has other refs:
    # the clone is populated, our branch simply is not there -> permanent.
    monkeypatch.setattr(
        "opal_server.git_fetcher.Repository",
        lambda path: _FakeRepo(_raise(KeyError("no such ref"))),
    )
    with pytest.raises(BranchHeadNotFoundError):
        _branch_head_fetcher(tmp_path)._get_current_branch_head()


def test_branch_head_transient_giterror_propagates(tmp_path, monkeypatch):
    # resolve_refish raises pygit2.GitError: ref present, object store gutted.
    # Must propagate (route -> 503), NOT become BranchHeadNotFoundError (409).
    monkeypatch.setattr(
        "opal_server.git_fetcher.Repository",
        lambda path: _FakeRepo(_raise(pygit2.GitError("odb: object not found"))),
    )
    with pytest.raises(pygit2.GitError):
        _branch_head_fetcher(tmp_path)._get_current_branch_head()


def test_branch_head_success_returns_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "opal_server.git_fetcher.Repository",
        lambda path: _FakeRepo(lambda: (_FakeCommit("deadbeef"), None)),
    )
    assert _branch_head_fetcher(tmp_path)._get_current_branch_head() == "deadbeef"


def test_transient_object_store_giterror_returns_retryable_503(tmp_path, monkeypatch):
    """End-to-end: a transient pygit2.GitError out of make_bundle -> 503, not 409."""
    live = _scope("live", "https://git/live.git")
    default = _scope("default", "https://git/default.git")
    repo = FakeScopeRepository([live, default])

    def fake_make_bundle(self, base_hash):
        if self._scope_id == "live":
            raise pygit2.GitError("odb: object not found")
        return _default_bundle()

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake_make_bundle)
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    resp = _client(repo, tmp_path).get("/scopes/live/policy")
    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "5"


def test_route_splits_clone_in_progress_from_wrong_branch(tmp_path, monkeypatch):
    """End-to-end, both verdicts, on the SAME route.

    Replaces an earlier version of this test that drove the split with the
    in-flight marker (`_mark_git_op_started`). That mechanism was wrong: the
    marker is per-process and leader-only, so it produced the right answer on
    one worker and the wrong one on the rest. The split is now disk-derived, so
    a test that fakes the marker would prove nothing.
    """
    from opal_server.git_fetcher import CloneNotPopulatedError

    live = _scope("live", "https://git/live.git")
    repo = FakeScopeRepository([live])
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    # The wait is off here on purpose: what this test pins is the VERDICT the
    # route reaches for each condition, and the wait only decides how long the
    # 503 verdict takes to arrive. Leaving it on would hold this test for the
    # full SCOPES_POLICY_CLONE_WAIT_SECONDS budget while asserting nothing
    # about it (scope_policy_clone_wait_test owns the hold itself).
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 0)
    client = _client(repo, tmp_path)

    # clone still being populated: no refs/remotes/<remote>/* on disk yet
    monkeypatch.setattr(
        GitPolicyFetcher,
        "make_bundle",
        lambda self, base_hash: (_ for _ in ()).throw(
            CloneNotPopulatedError("No refs/remotes/origin/* yet")
        ),
    )
    populating = client.get("/scopes/live/policy")

    # namespace populated, our branch simply absent: a real misconfiguration
    monkeypatch.setattr(
        GitPolicyFetcher,
        "make_bundle",
        lambda self, base_hash: (_ for _ in ()).throw(
            BranchHeadNotFoundError("Could not find current branch head")
        ),
    )
    misconfigured = client.get("/scopes/live/policy")

    assert populating.status_code == 503, "a clone in progress is not a config error"
    assert populating.headers["retry-after"] == "30"
    assert misconfigured.status_code == 409, "a wrong branch is not transient"
    assert "retry-after" not in {k.lower() for k in misconfigured.headers}


def test_branch_head_with_no_remote_refs_is_transient_not_permanent(
    tmp_path, monkeypatch
):
    """_clone() rmtree's the destination and clones INTO the final path, so for
    the whole duration of a recovery re-clone the dir exists with NO
    refs/remotes/<remote>/* at all. That is indistinguishable from a wrong
    branch by resolve_refish alone, and it is the opposite verdict.

    Mutation: dropping the listall_references check raises
    BranchHeadNotFoundError (the 409 path) and fails here.
    """
    from opal_server.git_fetcher import CloneNotPopulatedError

    monkeypatch.setattr(
        "opal_server.git_fetcher.Repository",
        lambda path: _FakeRepo(_raise(KeyError("no such ref")), refs=[]),
    )
    with pytest.raises(CloneNotPopulatedError):
        _branch_head_fetcher(tmp_path)._get_current_branch_head()


def test_mid_clone_503_is_identical_on_a_non_leader_worker(tmp_path, monkeypatch):
    """The 503/409 split must not depend on the in-flight marker.

    That marker is a per-process module global, written only by
    run_in_git_executor via fetch_and_notify_on_changes, whose only caller is
    sync_scope — and the watcher that drives sync is constructed under the
    leadership lock. GET /scopes/{id}/policy has no leader affinity, so on every
    NON-leader worker the marker is permanently empty. Keying the split on it
    answered 409 "not retryable" on N-1 of N workers throughout a recovery
    re-clone: the exact inversion the split exists to prevent.

    This test never sets the marker, so it IS the non-leader case.

    Mutation: reinstating `if git_op_in_flight(...)` as the discriminator in
    api.py returns 409 and fails here.
    """
    from opal_server.git_fetcher import CloneNotPopulatedError, git_op_in_flight

    live = _scope("live", "https://git/live.git")
    repo = FakeScopeRepository([live])
    sid = GitPolicyFetcher.source_id(live.policy)

    def fake_make_bundle(self, base_hash):
        raise CloneNotPopulatedError("No refs/remotes/origin/* yet")

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake_make_bundle)
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )
    # See the note in test_route_splits_clone_in_progress_from_wrong_branch:
    # the claim here is about WHICH verdict a non-leader reaches, not how long
    # it holds the request first.
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 0)

    assert not git_op_in_flight(sid), "this test must run as a non-leader"
    resp = _client(repo, tmp_path).get("/scopes/live/policy")

    assert resp.status_code == 503, "non-leader worker answered the wrong verdict"
    assert resp.headers["retry-after"] == "30"


def test_unknown_scope_without_a_default_is_404_not_500(tmp_path, monkeypatch):
    """A deployment with no "default" scope is ordinary — the git-leak bed is
    one. Asking for an unknown scope there re-raised ScopeNotFoundError out of
    the route, and nothing registers a handler for it, so it surfaced as an
    unhandled 500. get_scope and refresh_scope already answer 404.

    Mutation: restoring `raise ScopeNotFoundError(scope_id)` fails here.
    """
    repo = FakeScopeRepository([])  # no scopes at all, "default" included
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    resp = _client(repo, tmp_path).get("/scopes/ghost/policy")

    assert resp.status_code == 404, "unknown scope surfaced as a server error"
    assert "ghost" in resp.json()["detail"]


def test_default_bundle_build_does_not_block_the_event_loop(tmp_path, monkeypatch):
    """_generate_default_scope_bundle builds a full bundle: open the repo, walk
    the tree, read and encode every file. On the loop that stalls every other
    request this worker is serving.

    Asserts it is dispatched off-loop by checking make_bundle does not run on
    the loop's thread. Mutation: dropping run_sync fails here.
    """
    default = _scope("default", "https://git/default.git")
    repo = FakeScopeRepository([default])
    seen = {}

    def fake_make_bundle(self, base_hash):
        # asyncio.get_running_loop() succeeds ONLY on the thread running the
        # loop. In an executor thread it raises RuntimeError. That is the exact
        # discriminator; comparing thread NAMES is not — TestClient runs the
        # loop in a worker thread of its own, so "not MainThread" is true either
        # way and an earlier version of this test passed with run_sync removed.
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return _default_bundle()

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake_make_bundle)
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    resp = _client(repo, tmp_path).get("/scopes/ghost/policy")

    assert resp.status_code == 200
    assert seen["on_loop"] is False, (
        "the default bundle was built ON the event loop — every other request "
        "this worker is serving stalls for the whole build"
    )


def test_transient_fault_building_the_default_bundle_is_503_not_404(
    tmp_path, monkeypatch
):
    """A "default" scope that EXISTS but whose clone is momentarily unavailable
    is a transient fault, not "no such scope".

    These are the same exceptions the primary path answers with 503 forty lines
    up. Folding them into the 404 told a client to stop asking about a condition
    that self-heals in seconds, and §6 tells third-party consumers to act on
    these codes.

    Mutation: restoring the single wide `except (ScopeNotFoundError, ...)` tuple
    that maps everything to 404 fails here.
    """
    default = _scope("default", "https://git/default.git")
    repo = FakeScopeRepository([default])  # "default" EXISTS

    def fake_make_bundle(self, base_hash):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", fake_make_bundle)
    monkeypatch.setattr(
        "opal_server.scopes.api.opal_server_config.BASE_DIR", str(tmp_path)
    )

    resp = _client(repo, tmp_path).get("/scopes/ghost/policy")

    assert resp.status_code == 503, "a transient fault was reported as permanent"
    assert resp.headers["retry-after"] == "5"
