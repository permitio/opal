"""Scopes mode logs one INFO line per incremental policy push (PER-16361).

The kept line is ``NewCommitsCallbacks.trigger_notification``'s "Triggering
policy update for scope", logged once per publish by each pod leader. The other
lines of the push chain are DEBUG; their WARN/ERROR siblings keep their level.

The exactly-one-INFO tests cover ``on_update``, a ``sync_scope`` force-fetch (a
refresh without a hint) and ``sync_scopes`` (refresh-all, the periodic poll),
which adds its one per-pass line. Other paths keep their own INFO lines: a
scope's first sync, a hinted refresh and fetch anomalies. "INFO" means OPAL's
own loggers; third-party loggers are excluded.
"""

import datetime
from pathlib import Path

import git
import pygit2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_common.tests.log_capture import capture_records, starting_with
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import NewCommitsCallbacks, ScopesService

SCOPE_ID = "s1"
AUTHOR = git.Actor("test", "test@example.com")


class FakeScopeRepository:
    def __init__(self, scopes):
        self._scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self._scopes:
            raise ScopeNotFoundError(scope_id)
        return self._scopes[scope_id]

    async def all(self):
        return list(self._scopes.values())


class FakeAuthenticator:
    """Mimics a JWTAuthenticator whose verifier is disabled (no public key)."""

    enabled = False

    def __call__(self):
        return {}


class RecordingPubSub:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append((topics, data))


def _source(url="https://git.example.com/org/policy.git", poll_updates=False):
    return GitPolicyScopeSource(
        source_type="git", url=url, auth=NoAuthData(), poll_updates=poll_updates
    )


def _opal_records(records, level):
    return [
        r
        for r in records
        if r["level"].name == level
        and r["name"].startswith(("opal_server", "opal_common"))
    ]


def _commit(repo: git.Repo, relpath: str, contents: str) -> git.Commit:
    path = Path(repo.working_tree_dir) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    repo.index.add([relpath])
    return repo.index.commit(f"update {relpath}", author=AUTHOR, committer=AUTHOR)


@pytest.fixture
def clear_fetcher_caches():
    def clear():
        GitPolicyFetcher.repos.clear()
        GitPolicyFetcher.repo_locks.clear()
        GitPolicyFetcher.repos_last_fetched.clear()
        GitPolicyFetcher.source_backoff.clear()

    clear()
    yield
    clear()


@pytest.fixture
def scope_clone(tmp_path):
    """A repo where NewCommitsCallbacks looks for the scope's clone."""
    source = _source()
    repo = git.Repo.init(GitPolicyFetcher.repo_clone_path(tmp_path, source))
    return source, repo


@pytest.mark.asyncio
async def test_policy_push_logs_exactly_one_info_line(tmp_path, scope_clone):
    source, repo = scope_clone
    old = _commit(repo, "policy/a.rego", "package a\n")
    new = _commit(repo, "policy/a.rego", "package a\n\ndefault allow := false\n")
    pubsub = RecordingPubSub()
    callbacks = NewCommitsCallbacks(tmp_path, SCOPE_ID, source, pubsub)

    with capture_records() as logs:
        await callbacks.on_update(old.hexsha, new.hexsha)

    assert len(pubsub.published) == 1
    topics, _ = pubsub.published[0]
    assert topics and all(t.startswith(f"{SCOPE_ID}:") for t in topics)

    [info] = _opal_records(logs.emitted, "INFO")
    assert info["message"].startswith(f"Triggering policy update for scope {SCOPE_ID}")
    [found] = starting_with(logs.emitted, f"scope '{SCOPE_ID}': Found new commits")
    assert found["level"].name == "DEBUG"
    [publishing] = starting_with(logs.emitted, "Publishing to topics:")
    assert publishing["level"].name == "DEBUG"
    assert _opal_records(logs.emitted, "WARNING") == []
    assert _opal_records(logs.emitted, "ERROR") == []


@pytest.mark.asyncio
async def test_push_with_no_tracked_files_warns_and_does_not_publish(
    tmp_path, scope_clone
):
    source, repo = scope_clone
    old = _commit(repo, "README.txt", "one\n")
    new = _commit(repo, "README.txt", "two\n")
    pubsub = RecordingPubSub()
    callbacks = NewCommitsCallbacks(tmp_path, SCOPE_ID, source, pubsub)

    with capture_records() as logs:
        await callbacks.on_update(old.hexsha, new.hexsha)

    assert pubsub.published == []
    assert starting_with(logs.emitted, f"scope '{SCOPE_ID}': Found new commits")
    [warning] = starting_with(
        logs.emitted, "new commits detected but no tracked files were affected"
    )
    assert warning["level"].name == "WARNING"
    # "Found new commits" is DEBUG, so the scope has to travel on the warning.
    assert warning["extra"]["scope_id"] == SCOPE_ID
    assert not starting_with(logs.emitted, "Triggering policy update")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "clone_state, error_prefix",
    [
        ("missing", f"on_update({SCOPE_ID}) was triggered, but repo path is not found"),
        ("not a repo", "Got exception for repo in path"),
    ],
    ids=["missing", "not-a-repo"],
)
async def test_on_update_error_lines_stay_error(tmp_path, clone_state, error_prefix):
    source = _source()
    if clone_state == "not a repo":
        GitPolicyFetcher.repo_clone_path(tmp_path, source).mkdir(parents=True)
    pubsub = RecordingPubSub()
    callbacks = NewCommitsCallbacks(tmp_path, SCOPE_ID, source, pubsub)

    with capture_records() as logs:
        await callbacks.on_update("a" * 40, "b" * 40)

    assert pubsub.published == []
    assert starting_with(logs.emitted, f"scope '{SCOPE_ID}': Found new commits")
    [error] = starting_with(logs.emitted, error_prefix)
    assert error["level"].name == "ERROR"


@pytest.mark.asyncio
async def test_sync_scope_incremental_push_logs_exactly_one_info_line(
    tmp_path, clear_fetcher_caches
):
    """End to end from sync_scope on the incremental force-fetch path (repo
    found, fetched, new commits): a new INFO anywhere on it would show up."""
    remote = git.Repo.init(tmp_path / "remote", initial_branch="main")
    _commit(remote, "policy/a.rego", "package a\n")
    pubsub = RecordingPubSub()
    scope = Scope(scope_id=SCOPE_ID, policy=_source(url=str(tmp_path / "remote")))
    service = ScopesService(
        base_dir=tmp_path / "opal",
        scopes=FakeScopeRepository([scope]),
        pubsub_endpoint=pubsub,
    )
    await service.sync_scope(scope_id=SCOPE_ID)  # clones; the first sync
    assert len(pubsub.published) == 1
    _commit(remote, "policy/a.rego", "package a\n\ndefault allow := false\n")
    # Taken after the clone, so the refresh is newer than the last fetch.
    req_time = datetime.datetime.now()

    with capture_records() as logs:
        await service.sync_scope(scope_id=SCOPE_ID, force_fetch=True, req_time=req_time)

    assert len(pubsub.published) == 2
    [info] = _opal_records(logs.emitted, "INFO")
    assert info["message"].startswith(f"Triggering policy update for scope {SCOPE_ID}")
    assert _opal_records(logs.emitted, "WARNING") == []
    assert _opal_records(logs.emitted, "ERROR") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "only_poll_updates", [False, True], ids=["refresh-all", "periodic-poll"]
)
async def test_sync_scopes_push_logs_the_pass_line_and_one_info_line(
    tmp_path, clear_fetcher_caches, only_poll_updates
):
    """Refresh-all and the periodic poll go through sync_scopes: one per-pass
    INFO line, then one "Triggering policy update" per pushed scope."""
    remote = git.Repo.init(tmp_path / "remote", initial_branch="main")
    _commit(remote, "policy/a.rego", "package a\n")
    source = _source(url=str(tmp_path / "remote"), poll_updates=True)
    pubsub = RecordingPubSub()
    service = ScopesService(
        base_dir=tmp_path / "opal",
        scopes=FakeScopeRepository([Scope(scope_id=SCOPE_ID, policy=source)]),
        pubsub_endpoint=pubsub,
    )
    await service.sync_scopes(only_poll_updates=only_poll_updates)  # clones
    assert len(pubsub.published) == 1
    _commit(remote, "policy/a.rego", "package a\n\ndefault allow := false\n")

    with capture_records() as logs:
        await service.sync_scopes(only_poll_updates=only_poll_updates)

    assert len(pubsub.published) == 2
    [pass_line, info] = _opal_records(logs.emitted, "INFO")
    assert pass_line["message"].startswith("OPAL Scopes: syncing 1 scopes")
    assert info["message"].startswith(f"Triggering policy update for scope {SCOPE_ID}")
    assert _opal_records(logs.emitted, "WARNING") == []
    assert _opal_records(logs.emitted, "ERROR") == []


@pytest.mark.asyncio
async def test_duplicate_refresh_logs_no_info_line(tmp_path, clear_fetcher_caches):
    """A refresh whose request predates the last fetch is skipped at DEBUG."""
    remote = git.Repo.init(tmp_path / "remote", initial_branch="main")
    _commit(remote, "policy/a.rego", "package a\n")
    scope = Scope(scope_id=SCOPE_ID, policy=_source(url=str(tmp_path / "remote")))
    service = ScopesService(
        base_dir=tmp_path / "opal",
        scopes=FakeScopeRepository([scope]),
        pubsub_endpoint=RecordingPubSub(),
    )
    # Back a second, so a coarse clock can't stamp the clone at the same time.
    req_time = datetime.datetime.now() - datetime.timedelta(seconds=1)
    await service.sync_scope(scope_id=SCOPE_ID)  # clones; records the fetch time

    with capture_records() as logs:
        await service.sync_scope(scope_id=SCOPE_ID, force_fetch=True, req_time=req_time)

    [fetched] = starting_with(logs.emitted, "Repo was fetched after refresh request")
    assert fetched["level"].name == "DEBUG"
    assert not starting_with(logs.emitted, "Fetching remote")
    assert _opal_records(logs.emitted, "INFO") == []


def test_refresh_scope_line_is_debug_and_still_publishes(tmp_path):
    repo = FakeScopeRepository([Scope(scope_id=SCOPE_ID, policy=_source())])
    pubsub = RecordingPubSub()
    service = ScopesService(base_dir=tmp_path, scopes=repo, pubsub_endpoint=None)
    app = FastAPI()
    app.include_router(
        init_scope_router(repo, FakeAuthenticator(), pubsub, service),
        prefix="/scopes",
    )

    with capture_records() as logs:
        logger.info("deployed-level control")
        response = TestClient(app).post(f"/scopes/{SCOPE_ID}/refresh")

    assert response.status_code == 200
    [(topic, data)] = pubsub.published
    assert topic == opal_server_config.POLICY_REPO_WEBHOOK_TOPIC
    assert data["scope_id"] == SCOPE_ID and data["force_fetch"] is True
    [line] = starting_with(logs.emitted, f"Refresh scope: {SCOPE_ID}")
    assert line["level"].name == "DEBUG"
    assert starting_with(logs.deployed, "deployed-level control")
    assert not starting_with(logs.deployed, "Refresh scope:")


@pytest.mark.asyncio
async def test_already_fetched_line_is_debug_and_missing_branch_line_stays_info(
    tmp_path, clear_fetcher_caches
):
    source = _source()
    fetcher = GitPolicyFetcher(tmp_path, SCOPE_ID, source)
    req_time = datetime.datetime.now()
    GitPolicyFetcher.repos_last_fetched[
        GitPolicyFetcher.source_id(source)
    ] = req_time + datetime.timedelta(seconds=1)
    # Empty: no remote-tracking branch, so the target-branch check fetches.
    repo = pygit2.init_repository(str(tmp_path / "clone"))

    with capture_records() as logs:
        should_fetch = await fetcher._should_fetch(
            repo, force_fetch=True, req_time=req_time
        )

    assert should_fetch is True
    [fetched] = starting_with(logs.emitted, "Repo was fetched after refresh request")
    assert fetched["level"].name == "DEBUG"
    [missing] = starting_with(logs.emitted, "Target branch was not found")
    assert missing["level"].name == "INFO"
    assert starting_with(logs.deployed, "Target branch was not found")
    assert not starting_with(logs.deployed, "Repo was fetched after refresh request")


@pytest.mark.asyncio
async def test_hinted_hash_line_stays_info(tmp_path, clear_fetcher_caches):
    """A hinted commit absent from the clone triggers a fetch, at INFO."""
    remote = git.Repo.init(tmp_path / "remote", initial_branch="main")
    _commit(remote, "policy/a.rego", "package a\n")
    source = _source(url=str(tmp_path / "remote"))
    fetcher = GitPolicyFetcher(tmp_path / "opal", SCOPE_ID, source)
    await fetcher.fetch_and_notify_on_changes()  # clones
    clone = fetcher._get_repo()

    with capture_records() as logs:
        assert await fetcher._should_fetch(clone, hinted_hash="0" * 40) is True

    [hinted] = starting_with(logs.emitted, "Hinted commit hash was not found")
    assert hinted["level"].name == "INFO"
    assert starting_with(logs.deployed, "Hinted commit hash was not found")


@pytest.mark.asyncio
async def test_could_not_clone_line_stays_error(tmp_path, clear_fetcher_caches):
    """Clone failures stay ERROR: alerts key on this text at error status.

    The URL must not exist (an existing non-repo dir fails differently)
    and holds no ':' (which git reads as an SSH remote).
    """
    missing_remote = str(tmp_path / "no-such-remote")
    fetcher = GitPolicyFetcher(tmp_path / "opal", SCOPE_ID, _source(url=missing_remote))

    with capture_records() as logs:
        await fetcher.fetch_and_notify_on_changes()

    [error] = starting_with(logs.emitted, "Could not clone repo at")
    assert error["level"].name == "ERROR"
    assert starting_with(logs.deployed, "Could not clone repo at")
