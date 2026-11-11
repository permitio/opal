"""A policy bundle request with no base_hash, from a client that holds no
policy yet, fetches the scope's branch before it is served (the git command
line only).

A git command-line fetch asks only for the branches its syncs need, so a
server that missed a scope's refresh is not caught up by the fetches of
other scopes. A client starting from nothing would get that server's old
head. Now such a request asks every server for a forced sync of the
scope (the message a refresh sends), and waits up to
OPAL_SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS for this server's fetch,
read from the clone's fetch marks. A fetch that fails or runs past the
wait serves what the clone holds; a branch the clone does not have then
is a 503, and one the remote does not have after a fetch that succeeded
the 409.

Real clones of a local origin served over HTTP (conftest's git_http);
the leader is this test, which runs the sync a published request asks
for, or writes the marks itself.
"""

import asyncio
import datetime
import math
import os
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable, List, Optional

import httpx
import pytest
from fastapi import FastAPI
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server import git_fetcher
from opal_server.config import OpalServerConfig, opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, fetch_mark_after
from opal_server.scopes import api as scopes_api
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.scopes.service import ScopesService

pytestmark = pytest.mark.fetch_backend("cli")

_METRIC = "opal_server.scopes.policy_fresh_fetch"
_SECONDS_METRIC = "opal_server.scopes.policy_fresh_fetch_seconds"
_SYNC = {"scope_id": "live", "force_fetch": True, "honor_backoff": True}


class _Scopes:
    def __init__(self, scopes):
        self.scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self.scopes:
            raise ScopeNotFoundError(scope_id)
        return self.scopes[scope_id]

    async def all(self):
        return list(self.scopes.values())


class _Authenticator:
    enabled = False

    def __call__(self):
        return {}


class _Leader:
    """The pub/sub endpoint the route publishes to, standing in for every
    server's leader: each sync request published runs ``on_publish`` (in a task
    of its own, as the watcher's trigger does)."""

    def __init__(self) -> None:
        self.published: List[dict] = []
        self.on_publish: Optional[Callable] = None
        self.fail = False
        self.delay = 0.0
        self.tasks: List[asyncio.Future] = []

    async def publish(self, topics, data=None):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ConnectionError("broadcaster down")
        if topics == opal_server_config.POLICY_REPO_WEBHOOK_TOPIC:
            self.published.append(data)
            if self.on_publish is not None:
                self.tasks.append(asyncio.ensure_future(self.on_publish(data)))


class _Bed:
    def __init__(self, tmp_path: Path, url: str, branch: str) -> None:
        self.scope = Scope(
            scope_id="live",
            policy=GitPolicyScopeSource(
                source_type="git", url=url, branch=branch, auth=NoAuthData()
            ),
        )
        self.leader = _Leader()
        self.service = ScopesService(
            base_dir=tmp_path, scopes=_Scopes([self.scope]), pubsub_endpoint=self.leader
        )
        self.app = FastAPI()
        self.app.include_router(
            init_scope_router(
                _Scopes([self.scope]), _Authenticator(), self.leader, self.service
            ),
            prefix="/scopes",
        )
        self.clone = GitPolicyFetcher.repo_clone_path(tmp_path, self.scope.policy)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    def sync_after(self, delay: float) -> Callable:
        """A leader that runs the sync asked for ``delay`` seconds later."""

        async def run(data):
            await asyncio.sleep(delay)
            await self.service.sync_scope(
                scope_id=data["scope_id"],
                force_fetch=data["force_fetch"],
                honor_backoff=data["honor_backoff"],
                req_time=datetime.datetime.now(),
                fresh_within=data.get("fresh_within"),
            )

        return run

    def mark_after(self, delay: float, name: str) -> Callable:
        """A leader whose fetch writes the mark ``name`` ``delay`` seconds
        later, dated then."""

        async def run(data):
            await asyncio.sleep(delay)
            git_fetcher._write_fetch_marks(
                self.clone / ".git" / "opal-fetched", [name], time.time()
            )

        return run


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_REPACK_PACK_LIMIT", 0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT", 64)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL", 60.0
    )
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS", 5.0
    )
    monkeypatch.setattr(scopes_api, "_CLONE_WAIT_POLL_SECONDS", 0.02)
    monkeypatch.setattr(scopes_api, "_FRESH_FETCH_POLL_SECONDS", 0.02)
    monkeypatch.setattr(scopes_api, "_clone_wait_inflight", 0)
    monkeypatch.setattr(scopes_api, "_fresh_fetch_clamp_logged", False)
    monkeypatch.setattr(scopes_api, "_branch_refresh_requested", OrderedDict())
    monkeypatch.setattr(scopes_api, "_fresh_fetch_claims", OrderedDict())
    monkeypatch.setattr(scopes_api, "_branch_refresh_publishes", set())
    monkeypatch.setattr(scopes_api, "_branch_refresh_failed_claims", OrderedDict())
    monkeypatch.setattr(git_fetcher, "_repacks_due", {})
    monkeypatch.setattr(git_fetcher, "_fetch_marks_warned", set())
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()
    yield
    assert scopes_api._clone_wait_inflight == 0, "a wait slot leaked"
    GitPolicyFetcher.reset_caches()
    GitPolicyFetcher.source_backoff.clear()


@pytest.fixture
def emitted(monkeypatch):
    calls = {"increment": [], "gauge": []}
    monkeypatch.setattr(
        metrics,
        "increment",
        lambda metric, tags=None: calls["increment"].append((metric, tags)),
    )
    monkeypatch.setattr(
        metrics,
        "gauge",
        lambda metric, value, tags=None: calls["gauge"].append((metric, value, tags)),
    )
    monkeypatch.setattr(metrics, "event", lambda *a, **k: None)
    return calls


@pytest.fixture
def records():
    seen = []
    sink = logger.add(lambda m: seen.append(m.record), level="DEBUG")
    yield seen
    logger.remove(sink)


def _published(bed: _Bed) -> List[dict]:
    """The sync requests published, without the fresh_within each carries (the
    wait: see test_a_bundle_without_base_hash_waits_for_this_pods_fetch)."""
    return [
        {k: v for k, v in data.items() if k != "fresh_within"}
        for data in bed.leader.published
    ]


def _outcomes(emitted) -> List[str]:
    return [
        tags["outcome"] for metric, tags in emitted["increment"] if metric == _METRIC
    ]


async def _bed(
    tmp_path, git_http, make_origin, branch: str = "master", aged: bool = True
):
    """A scope on ``branch`` of a served origin, whose clone this server has
    (made by a sync, as the leader makes it), dated an hour back unless not
    ``aged``; the origin and the head the clone holds."""
    origin = make_origin(git_http.root / "repo.git")
    bed = _Bed(tmp_path, git_http.url("repo.git"), branch)
    await bed.service.sync_scope(scope_id="live")
    assert bed.clone.is_dir()
    if aged:
        _cloned_an_hour_ago(bed)
    return bed, origin, str(origin.repo.references["refs/heads/master"].target)


def _cloned_an_hour_ago(bed: _Bed) -> None:
    """Date the clone, its marks and the leader's record of it an hour back."""
    hour = 3600
    marks = bed.clone / ".git" / "opal-fetched"
    for mark in marks.iterdir() if marks.is_dir() else ():
        dated = mark.stat().st_mtime - hour
        os.utime(mark, (dated, dated))
    source_id = GitPolicyFetcher.source_id(bed.scope.policy)
    GitPolicyFetcher.repos_last_fetched[source_id] -= datetime.timedelta(seconds=hour)


async def _get(bed: _Bed, **params) -> httpx.Response:
    async with bed.client() as client:
        try:
            return await client.get("/scopes/live/policy", params=params)
        finally:
            await asyncio.gather(*bed.leader.tasks, return_exceptions=True)


# --- the wait -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_bundle_without_base_hash_waits_for_this_pods_fetch(
    tmp_path, git_http, make_origin, emitted
):
    bed, origin, _ = await _bed(tmp_path, git_http, make_origin)
    new = origin.commit("master")
    bed.leader.on_publish = bed.sync_after(0.3)

    r = await _get(bed)

    assert _published(bed) == [_SYNC]
    assert bed.leader.published[0]["fresh_within"] == 5.0
    assert r.status_code == 200, r.text
    assert r.json()["hash"] == new
    assert _outcomes(emitted) == ["fetched"]
    (waited,) = [v for m, v, t in emitted["gauge"] if m == _SECONDS_METRIC]
    assert 0.3 <= waited < 5


@pytest.mark.asyncio
async def test_a_delta_request_publishes_nothing(
    tmp_path, git_http, make_origin, emitted
):
    bed, origin, old = await _bed(tmp_path, git_http, make_origin)
    origin.commit("master")

    r = await _get(bed, base_hash=old)

    assert r.status_code == 200, r.text
    assert bed.leader.published == []
    assert _outcomes(emitted) == []


@pytest.mark.asyncio
async def test_a_fetch_past_the_wait_serves_the_clones_head(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS", 0.5
    )
    bed, origin, old = await _bed(tmp_path, git_http, make_origin)
    origin.commit("master")

    started = time.monotonic()
    r = await _get(bed)

    assert 0.5 <= time.monotonic() - started < 2
    assert r.status_code == 200, r.text
    assert r.json()["hash"] == old
    assert _outcomes(emitted) == ["timeout"]


@pytest.mark.asyncio
async def test_a_failed_fetch_ends_the_wait_at_once(
    tmp_path, git_http, make_origin, emitted
):
    bed, origin, old = await _bed(tmp_path, git_http, make_origin)
    origin.commit("master")
    bed.leader.on_publish = bed.mark_after(0.1, "FAILED")

    started = time.monotonic()
    r = await _get(bed)

    assert time.monotonic() - started < 2
    assert r.status_code == 200, r.text
    assert r.json()["hash"] == old
    assert _outcomes(emitted) == ["failed"]


@pytest.mark.asyncio
async def test_a_fetch_the_remote_refuses_ends_the_wait_at_once(
    tmp_path, git_http, make_origin, emitted
):
    """End to end: the leader's real fetch fails, and writes the FAILED mark."""
    bed, origin, old = await _bed(tmp_path, git_http, make_origin)
    origin.commit("master")
    git_http.error = "refused for the test"
    bed.leader.on_publish = bed.sync_after(0.0)

    started = time.monotonic()
    r = await _get(bed)

    assert time.monotonic() - started < 3
    assert r.status_code == 200, r.text
    assert r.json()["hash"] == old
    assert _outcomes(emitted) == ["failed"]


@pytest.mark.asyncio
async def test_a_mark_from_before_the_request_does_not_count(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    """Success marks (the branch's, ALL) dated within the wait before the
    request: the fetch they mark may predate a push since.

    Mutation: counting a success that started within the wait before the
    request answers it at once ("fetched").
    """
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS", 0.3
    )
    bed, origin, old = await _bed(tmp_path, git_http, make_origin)
    marks = bed.clone / ".git" / "opal-fetched"
    before = time.time() - 0.1
    git_fetcher._write_fetch_marks(
        marks, ["ALL", git_fetcher._fetch_mark_name("master")], before
    )

    r = await _get(bed)

    assert r.status_code == 200, r.text
    assert _published(bed) == [_SYNC]
    assert _outcomes(emitted) == ["timeout"]


@pytest.mark.asyncio
async def test_a_failure_within_the_wait_before_the_request_answers_it_at_once(
    tmp_path, git_http, make_origin, emitted
):
    """A fetch of the branch that failed within the wait before the request:
    the source is in its failure backoff, which the sync asked for would
    honour, so the clone's head is served at once, with nothing published.
    A fetch that succeeded after that failure (and before the request) does
    not answer it: the request asks for a fetch.

    Mutation: answering only from fetches after the request publishes a
    sync request per request while the source fails.
    """
    bed, origin, old = await _bed(tmp_path, git_http, make_origin)
    new = origin.commit("master")
    marks = bed.clone / ".git" / "opal-fetched"
    failed_at = time.time() - 1
    git_fetcher._write_fetch_marks(
        marks, [git_fetcher._fetch_failed_mark_name("master")], failed_at
    )

    r = await _get(bed)

    assert r.status_code == 200, r.text
    assert r.json()["hash"] == old
    assert bed.leader.published == []
    assert _outcomes(emitted) == ["failed"]

    git_fetcher._write_fetch_marks(
        marks, [git_fetcher._fetch_mark_name("master")], failed_at + 0.5
    )
    bed.leader.on_publish = bed.sync_after(0.0)

    r = await _get(bed)

    assert r.json()["hash"] == new
    assert _published(bed) == [_SYNC]
    assert _outcomes(emitted) == ["failed", "fetched"]


@pytest.mark.asyncio
async def test_requests_for_one_scope_share_one_publish(
    tmp_path, git_http, make_origin, emitted
):
    bed, origin, _ = await _bed(tmp_path, git_http, make_origin)
    new = origin.commit("master")
    bed.leader.on_publish = bed.sync_after(0.3)

    async with bed.client() as client:
        first, second = await asyncio.gather(
            client.get("/scopes/live/policy"), client.get("/scopes/live/policy")
        )
    await asyncio.gather(*bed.leader.tasks)

    assert _published(bed) == [_SYNC]
    assert [first.json()["hash"], second.json()["hash"]] == [new, new]
    assert _outcomes(emitted) == ["fetched", "fetched"]


@pytest.mark.asyncio
async def test_a_request_after_its_claims_fetch_ended_asks_again(
    tmp_path, git_http, make_origin, emitted
):
    """A request within the wait of another's sync request, once the fetch that
    one asked for has ended: that fetch started before this request, so it
    asks for a fetch of its own, and is served a commit pushed in between.

    Mutation: riding a claim younger than the wait whatever its fetch did
    serves the second request the first one's head.
    """
    bed, origin, _ = await _bed(tmp_path, git_http, make_origin)
    first_head = origin.commit("master")
    bed.leader.on_publish = bed.sync_after(0.0)
    first = await _get(bed)
    second_head = origin.commit("master")

    second = await _get(bed)

    assert [first.json()["hash"], second.json()["hash"]] == [first_head, second_head]
    assert _published(bed) == [_SYNC, _SYNC]
    assert _outcomes(emitted) == ["fetched", "fetched"]


@pytest.mark.asyncio
async def test_a_request_while_its_claims_fetch_runs_rides_it(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    """A second request that arrives while the fetch the first one asked for
    runs takes that fetch, though it started before the second: one sync
    request, one fetch.

    Mutation: never riding a claim publishes twice and fetches twice.
    """
    bed, origin, _ = await _bed(tmp_path, git_http, make_origin)
    new = origin.commit("master")
    calls = []
    running = asyncio.Event()
    real = git_fetcher.cli_fetch

    async def slow(*args, **kwargs):
        calls.append(kwargs)
        running.set()
        await asyncio.sleep(0.4)
        return await real(*args, **kwargs)

    monkeypatch.setattr(git_fetcher, "cli_fetch", slow)
    bed.leader.on_publish = bed.sync_after(0.0)

    async with bed.client() as client:
        first = asyncio.ensure_future(client.get("/scopes/live/policy"))
        await running.wait()
        second = await client.get("/scopes/live/policy")
        await first
    await asyncio.gather(*bed.leader.tasks)

    assert len(calls) == 1
    assert _published(bed) == [_SYNC]
    assert [first.result().json()["hash"], second.json()["hash"]] == [new, new]
    assert _outcomes(emitted) == ["fetched", "fetched"]


@pytest.mark.asyncio
async def test_a_claim_made_while_a_request_reads_the_marks_is_ridden(
    monkeypatch, tmp_path
):
    """Two requests that find one claim's fetch ended make one new claim: the
    one still reading the marks when the other made it rides it.

    Mutation: not reading the claim again after the marks publishes twice.
    """
    loop = asyncio.get_running_loop()
    scopes_api._fresh_fetch_claims["live"] = loop.time() - 1
    newer = loop.time()
    reads = []

    async def read_marks(func, *args):
        reads.append(args)
        if len(reads) == 1:
            scopes_api._fresh_fetch_claims["live"] = newer
            return True
        return None

    monkeypatch.setattr(scopes_api, "run_sync", read_marks)
    published = []

    async def publish() -> None:
        published.append(True)

    claim, ended = await scopes_api._fresh_fetch_claim(
        "live", publish, loop.time(), 5.0, repo_path=tmp_path, branch="master"
    )

    assert (claim, ended) == (newer, None)
    assert published == []
    assert len(reads) == 2


@pytest.mark.asyncio
async def test_a_claim_older_than_the_wait_publishes_again(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS", 0.2
    )
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)

    await _get(bed)
    await _get(bed)

    assert _published(bed) == [_SYNC, _SYNC]
    assert _outcomes(emitted) == ["timeout", "timeout"]


# --- a storm of clients starting ---------------------------------------------------


@pytest.fixture
def cli_fetches(monkeypatch):
    """How many git command-line fetches this server ran."""
    calls = []
    real = git_fetcher.cli_fetch

    async def fetch(*args, **kwargs):
        calls.append(kwargs)
        return await real(*args, **kwargs)

    monkeypatch.setattr(git_fetcher, "cli_fetch", fetch)
    return calls


@pytest.mark.asyncio
async def test_a_branch_pushed_after_a_clone_that_started_before_the_request_is_fetched(
    tmp_path, git_http, make_origin, emitted, cli_fetches
):
    """A scope's clone (its ALL mark) dated within the wait before the request,
    and the scope's branch pushed after the clone: the request asks for a
    fetch, and is served the branch, not the 409 of a branch missing after a
    fetch.

    Mutation: counting a clone or fetch that started within the wait before
    the request answers it from the clone, which lacks the branch: 409.
    """
    bed, origin, _ = await _bed(
        tmp_path, git_http, make_origin, branch="cold", aged=False
    )
    origin.branch("cold")
    head = origin.commit("cold")
    bed.leader.on_publish = bed.sync_after(0.0)

    r = await _get(bed)

    assert r.status_code == 200, r.text
    assert r.json()["hash"] == head
    assert _published(bed) == [_SYNC]
    assert len(cli_fetches) == 1
    assert _outcomes(emitted) == ["fetched"]


@pytest.mark.asyncio
async def test_a_fetch_that_ended_before_the_request_does_not_answer_it(
    tmp_path, git_http, make_origin, emitted, cli_fetches
):
    """A fetch of the branch that ended just before the request, and a commit
    pushed after it: the request asks for a fetch of its own and is served
    that commit."""
    bed, origin, _ = await _bed(tmp_path, git_http, make_origin)
    await bed.service.sync_scope(
        scope_id="live", force_fetch=True, req_time=datetime.datetime.now()
    )
    assert len(cli_fetches) == 1
    new = origin.commit("master")
    bed.leader.on_publish = bed.sync_after(0.0)

    r = await _get(bed)

    assert r.json()["hash"] == new
    assert _published(bed) == [_SYNC]
    assert len(cli_fetches) == 2
    assert _outcomes(emitted) == ["fetched"]


@pytest.mark.asyncio
async def test_a_cold_start_sync_fetches_after_a_fetch_that_started_before_it(
    tmp_path, git_http, make_origin, cli_fetches
):
    """On the leader: a fetch of the branch that started before the sync a
    client with no policy asked for does not answer it, however recent.

    Mutation: answering it from a fetch within fresh_within does not fetch.
    """
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    now = datetime.datetime.now
    await bed.service.sync_scope(scope_id="live", force_fetch=True, req_time=now())
    assert len(cli_fetches) == 1

    await bed.service.sync_scope(
        scope_id="live", force_fetch=True, req_time=now(), fresh_within=10.0
    )
    assert len(cli_fetches) == 2


@pytest.mark.asyncio
async def test_a_storm_of_clients_costs_one_fetch_after_another(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    """100 clients start over about a second, each fetch taking 0.1 s or more.

    The requests that arrive before the fetch they asked for has ended take
    it, and the first one after it asks again: one sync request per fetch
    that ended, plus the first, and this server fetches one fetch after
    another, so at most one per 0.1 s.

    Mutation: never riding a claim makes a sync request per client.
    """
    hold = 0.1
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS", 5.0
    )
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    fetches = []
    real = git_fetcher.cli_fetch

    async def held(*args, **kwargs):
        fetches.append(kwargs)
        await asyncio.sleep(hold)
        return await real(*args, **kwargs)

    monkeypatch.setattr(git_fetcher, "cli_fetch", held)
    bed.leader.on_publish = bed.sync_after(0.0)

    started = time.monotonic()
    async with bed.client() as client:
        requests = []
        for _ in range(100):
            requests.append(asyncio.ensure_future(client.get("/scopes/live/policy")))
            await asyncio.sleep(0.01)
        answers = await asyncio.gather(*requests)
    await asyncio.gather(*bed.leader.tasks)
    took = time.monotonic() - started

    published = len(bed.leader.published)
    assert {a.status_code for a in answers} == {200}
    assert published - 1 <= len(fetches) <= published
    assert published <= math.ceil(took / hold) + 2
    assert _outcomes(emitted) == ["fetched"] * 100


@pytest.mark.asyncio
async def test_a_fetch_that_started_before_a_request_and_ended_after_it_does_not_count(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    """A refresh's fetch that started before the request and ends after it,
    and a commit pushed while it runs: the request's sync waits for the
    clone, fetches again, and the request is served the commit.

    Mutation: counting a fetch that started within the wait before the
    request serves the head that fetch brought, with one fetch.
    """
    bed, origin, _ = await _bed(tmp_path, git_http, make_origin)
    calls = []
    fetched = asyncio.Event()
    real = git_fetcher.cli_fetch

    async def slow_first(*args, **kwargs):
        calls.append(kwargs)
        result = await real(*args, **kwargs)
        if len(calls) == 1:
            fetched.set()
            await asyncio.sleep(0.5)
        return result

    monkeypatch.setattr(git_fetcher, "cli_fetch", slow_first)
    bed.leader.on_publish = bed.sync_after(0.0)
    refresh = asyncio.ensure_future(
        bed.service.sync_scope(
            scope_id="live", force_fetch=True, req_time=datetime.datetime.now()
        )
    )
    await fetched.wait()
    new = origin.commit("master")

    r = await _get(bed)
    await refresh

    assert r.json()["hash"] == new
    assert len(calls) == 2
    assert _published(bed) == [_SYNC]
    assert _outcomes(emitted) == ["fetched"]


@pytest.mark.asyncio
async def test_the_watcher_hands_the_sync_its_fresh_within(monkeypatch, tmp_path):
    """What the leader's watcher does with a published sync request."""
    import opal_server.scopes.task as task_module

    monkeypatch.setattr(task_module, "RedisDB", lambda url: None)
    monkeypatch.setattr(task_module, "ScopeRepository", lambda db: _Scopes([]))
    watcher = task_module.ScopesPolicyWatcherTask(_Leader())
    seen = {}

    async def sync_scope(**kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr(watcher._service, "sync_scope", sync_scope)

    await watcher.trigger(None, {**_SYNC, "fresh_within": 2.5})

    assert seen["fresh_within"] == 2.5
    assert seen["force_fetch"] is True and seen["honor_backoff"] is True


@pytest.mark.parametrize(
    "published, used",
    [
        (10, 10.0),
        (100, 55.0),
        (0, None),
        (-1, None),
        ("nan", None),
        ("x", None),
        (None, None),
    ],
)
def test_a_sync_takes_a_sane_fresh_within_only(published, used):
    assert git_fetcher._bounded_fresh_within(published) == used


@pytest.mark.asyncio
async def test_a_failed_fetch_of_another_branch_does_not_end_the_wait(
    tmp_path, git_http, make_origin, emitted
):
    """Only a failure of a fetch that asked for this branch ends the wait."""
    bed, origin, _ = await _bed(tmp_path, git_http, make_origin)
    new = origin.commit("master")
    other = GitPolicyScopeSource(
        source_type="git", url=bed.scope.policy.url, branch="other", auth=NoAuthData()
    )

    async def leader(data):
        git_http.error = "refused for the test"
        try:
            await GitPolicyFetcher(
                tmp_path, "other-scope", other
            ).fetch_and_notify_on_changes(
                force_fetch=True, req_time=datetime.datetime.now()
            )
        except Exception:
            pass
        finally:
            git_http.error = None
        GitPolicyFetcher.source_backoff.clear()
        await asyncio.sleep(0.3)
        await bed.sync_after(0.0)(data)

    bed.leader.on_publish = leader

    r = await _get(bed)

    assert _outcomes(emitted) == ["fetched"]
    assert r.json()["hash"] == new


@pytest.mark.asyncio
async def test_a_request_riding_a_claim_whose_publish_failed_stops_waiting(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS", 3.0
    )
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    bed.leader.delay = 0.3
    bed.leader.fail = True

    started = time.monotonic()
    async with bed.client() as client:
        first = asyncio.ensure_future(client.get("/scopes/live/policy"))
        await asyncio.sleep(0.1)
        second = await client.get("/scopes/live/policy")
        await first

    assert time.monotonic() - started < 2
    assert second.status_code == 200, second.text
    assert sorted(_outcomes(emitted)) == ["published_failed", "published_failed"]


@pytest.mark.asyncio
async def test_a_publish_slower_than_the_wait_gives_its_claim_back_when_it_fails(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS", 0.3
    )
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    bed.leader.delay = 0.6
    bed.leader.fail = True

    r = await _get(bed)
    assert "live" in scopes_api._fresh_fetch_claims
    await _until_publishes_end()

    assert r.status_code == 200, r.text
    assert _outcomes(emitted) == ["timeout"]
    assert "live" not in scopes_api._fresh_fetch_claims


async def _until_publishes_end() -> None:
    deadline = time.monotonic() + 5
    while scopes_api._branch_refresh_publishes:
        assert time.monotonic() < deadline, "a publish never ended"
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_a_cancelled_request_frees_its_slot_and_is_counted_cancelled(
    tmp_path, git_http, make_origin, emitted
):
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    fetcher = GitPolicyFetcher(tmp_path, "live", bed.scope.policy)
    waiting = asyncio.ensure_future(
        scopes_api._fresh_fetch_wait(
            fetcher,
            bed.clone,
            "live",
            None,
            lambda: bed.leader.publish(
                opal_server_config.POLICY_REPO_WEBHOOK_TOPIC, _SYNC
            ),
        )
    )
    await asyncio.sleep(0.2)
    assert scopes_api._clone_wait_inflight == 1

    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting

    assert scopes_api._clone_wait_inflight == 0
    assert _outcomes(emitted) == ["cancelled"]


@pytest.mark.asyncio
async def test_no_wait_while_too_many_publishes_are_pending(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    monkeypatch.setattr(scopes_api, "_BRANCH_REFRESH_PUBLISHES_MAX", 0)
    bed, _, old = await _bed(tmp_path, git_http, make_origin)

    r = await _get(bed)

    assert r.json()["hash"] == old
    assert bed.leader.published == []
    assert _outcomes(emitted) == ["shed"]


@pytest.mark.asyncio
async def test_the_route_answers_503_to_a_client_that_left_during_the_wait(
    tmp_path, git_http, make_origin, monkeypatch
):
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)

    async def left(*args, **kwargs):
        return "disconnected"

    monkeypatch.setattr(scopes_api, "_fresh_fetch_wait", left)

    r = await _get(bed)

    assert r.status_code == 503, r.text
    assert r.headers["retry-after"] == "5"


@pytest.mark.asyncio
async def test_the_waits_of_one_request_stay_within_the_ceiling(
    tmp_path, git_http, make_origin, monkeypatch
):
    """What the fresh wait took comes off the clone wait's 55 s."""
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    seen = {}
    real_build = scopes_api._make_bundle_waiting_for_clone

    async def slow_wait(*args, **kwargs):
        await asyncio.sleep(0.3)
        return "timeout"

    async def build(*args, **kwargs):
        seen["max_wait"] = kwargs["max_wait"]
        return await real_build(*args, **kwargs)

    monkeypatch.setattr(scopes_api, "_fresh_fetch_wait", slow_wait)
    monkeypatch.setattr(scopes_api, "_make_bundle_waiting_for_clone", build)

    await _get(bed)

    assert seen["max_wait"] <= scopes_api._CLONE_WAIT_MAX_SECONDS - 0.3


@pytest.mark.asyncio
async def test_a_clone_wait_is_held_no_longer_than_its_max_wait(monkeypatch, tmp_path):
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 5.0)

    def populating(self, base_hash=None):
        raise git_fetcher.CloneNotPopulatedError("No refs yet")

    monkeypatch.setattr(GitPolicyFetcher, "make_bundle", populating)
    fetcher = GitPolicyFetcher(
        tmp_path, "live", _Bed(tmp_path, "https://git.example/r.git", "m").scope.policy
    )

    started = time.monotonic()
    with pytest.raises(git_fetcher.CloneNotPopulatedError):
        await scopes_api._make_bundle_waiting_for_clone(
            fetcher, None, "live", max_wait=0.2
        )

    assert time.monotonic() - started < 1


# --- the branch -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_missing_branch_after_an_incomplete_fetch_is_503(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS", 0.3
    )
    bed, origin, _ = await _bed(tmp_path, git_http, make_origin, branch="later")

    r = await _get(bed)

    assert r.status_code == 503, r.text
    assert r.headers["retry-after"] == "5"
    assert r.json()["detail"] == (
        "Policy branch for scope live is not in this server's clone yet, retry shortly"
    )
    assert _published(bed) == [_SYNC]
    assert _outcomes(emitted) == ["timeout"]


@pytest.mark.asyncio
async def test_a_missing_branch_after_a_failed_fetch_is_503(
    tmp_path, git_http, make_origin, emitted
):
    bed, _, _ = await _bed(tmp_path, git_http, make_origin, branch="later")
    bed.leader.on_publish = bed.mark_after(0.0, "FAILED")

    r = await _get(bed)

    assert r.status_code == 503, r.text
    assert r.headers["retry-after"] == "5"
    assert _outcomes(emitted) == ["failed"]


@pytest.mark.asyncio
async def test_a_missing_branch_after_a_fetch_is_409(
    tmp_path, git_http, make_origin, emitted
):
    """The remote has no such branch: the 409 at once, without the branch wait
    of SCOPES_POLICY_BRANCH_REFRESH_INTERVAL and its second sync request."""
    bed, _, _ = await _bed(tmp_path, git_http, make_origin, branch="nope")
    bed.leader.on_publish = bed.sync_after(0.0)

    r = await _get(bed)

    assert r.status_code == 409, r.text
    assert _published(bed) == [_SYNC]
    assert _outcomes(emitted) == ["fetched"]
    assert not scopes_api._branch_refresh_requested.get(
        ("branch", "live", GitPolicyFetcher.source_id(bed.scope.policy), "nope")
    )


def _shed_at_the_cap(monkeypatch) -> None:
    """The fresh-fetch wait finds its one slot held by another request, which
    is answered before this request's bundle is built."""
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT", 1)
    fresh_fetch_wait = scopes_api._fresh_fetch_wait

    async def while_another_request_holds_the_slot(*args, **kwargs):
        scopes_api._clone_wait_inflight += 1
        try:
            return await fresh_fetch_wait(*args, **kwargs)
        finally:
            scopes_api._clone_wait_inflight -= 1

    monkeypatch.setattr(
        scopes_api, "_fresh_fetch_wait", while_another_request_holds_the_slot
    )


@pytest.mark.asyncio
async def test_a_missing_branch_shed_at_the_cap_is_409_at_once(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    """No slot is free when the request comes, and a fetch of the branch
    succeeded within the wait before it: the 409 at once.

    Served without waiting and with nothing published, though the request
    that held the slot is answered before this one's bundle is built: the
    branch wait of SCOPES_POLICY_BRANCH_REFRESH_INTERVAL does not hold it
    for the whole clone wait.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 2.0)
    _shed_at_the_cap(monkeypatch)
    bed, _, _ = await _bed(tmp_path, git_http, make_origin, branch="nope")
    bed.leader.on_publish = bed.sync_after(0.0)
    git_fetcher._write_fetch_marks(
        bed.clone / ".git" / "opal-fetched",
        [git_fetcher._fetch_mark_name("nope")],
        time.time() - 1,
    )

    started = time.monotonic()
    r = await _get(bed)
    took = time.monotonic() - started

    assert r.status_code == 409, r.text
    assert took < 1
    assert bed.leader.published == []
    assert _outcomes(emitted) == ["shed"]


@pytest.mark.asyncio
async def test_a_branch_shed_at_the_cap_while_its_fetch_hangs_is_503_at_once(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    """The remote has the branch, and no fetch of it on this server has ended
    within the wait (it hangs: nothing marks it).

    A request shed at the cap cannot tell that the branch is missing, so
    it gets 503 Retry-After 5 at once, not the 409 that tells a client
    its branch is not pushed.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_SECONDS", 2.0)
    _shed_at_the_cap(monkeypatch)
    bed, origin, _ = await _bed(tmp_path, git_http, make_origin, branch="later")
    origin.branch("later")

    started = time.monotonic()
    r = await _get(bed)
    took = time.monotonic() - started

    answer = (
        f"{r.status_code} Retry-After {r.headers.get('retry-after')} after {took:.2f}s"
    )
    assert (r.status_code, r.headers.get("retry-after")) == (503, "5"), answer
    assert took < 1, answer
    assert bed.leader.published == []
    assert _outcomes(emitted) == ["shed"]


@pytest.mark.asyncio
async def test_a_branch_pushed_after_the_clone_is_served_by_the_fetch(
    tmp_path, git_http, make_origin, emitted
):
    bed, origin, _ = await _bed(tmp_path, git_http, make_origin, branch="later")
    origin.branch("later")
    head = origin.commit("later")
    bed.leader.on_publish = bed.sync_after(0.1)

    r = await _get(bed)

    assert r.status_code == 200, r.text
    assert r.json()["hash"] == head
    assert _outcomes(emitted) == ["fetched"]


# --- when it does not wait --------------------------------------------------------


@pytest.mark.parametrize(
    "backend, wait",
    [("libgit2", 5.0), ("cli", 0.0), ("cli", -1.0), ("cli", math.nan)],
    ids=["libgit2", "0", "negative", "nan"],
)
@pytest.mark.asyncio
async def test_libgit2_and_a_wait_of_0_never_wait(
    backend, wait, tmp_path, git_http, make_origin, emitted, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", backend == "cli"
    )
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS", wait
    )
    bed, origin, old = await _bed(tmp_path, git_http, make_origin)
    origin.commit("master")

    r = await _get(bed)

    assert r.status_code == 200, r.text
    assert r.json()["hash"] == old
    assert bed.leader.published == []
    assert _outcomes(emitted) == []


@pytest.mark.asyncio
async def test_no_wait_without_a_landed_clone(tmp_path, git_http, make_origin, emitted):
    """No clone: the clone wait covers it, and the branch wait asks for the
    clone (a sync that is not forced)."""
    make_origin(git_http.root / "repo.git")
    bed = _Bed(tmp_path, git_http.url("repo.git"), "master")

    await _get(bed)

    assert _SYNC not in _published(bed)
    assert _outcomes(emitted) == []


@pytest.mark.asyncio
async def test_no_wait_for_a_branch_that_cannot_be_a_ref(
    tmp_path, git_http, make_origin, emitted
):
    bed, _, _ = await _bed(tmp_path, git_http, make_origin, branch="x~1")

    r = await _get(bed)

    assert r.status_code == 409, r.text
    assert bed.leader.published == []
    assert _outcomes(emitted) == []


@pytest.mark.asyncio
async def test_the_wait_holds_a_slot_of_the_clone_wait_cap(
    tmp_path, git_http, make_origin, emitted, monkeypatch
):
    bed, origin, old = await _bed(tmp_path, git_http, make_origin)
    seen = []

    async def observe(data):
        seen.append(scopes_api._clone_wait_inflight)
        git_fetcher._write_fetch_marks(
            bed.clone / ".git" / "opal-fetched", ["ALL"], time.time()
        )

    bed.leader.on_publish = observe
    await _get(bed)
    assert seen == [1]
    _cloned_an_hour_ago(bed)

    monkeypatch.setattr(opal_server_config, "SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT", 1)
    monkeypatch.setattr(scopes_api, "_clone_wait_inflight", 1)
    try:
        r = await _get(bed)
    finally:
        scopes_api._clone_wait_inflight = 0

    assert r.status_code == 200, r.text
    assert len(bed.leader.published) == 1
    assert _outcomes(emitted) == ["fetched", "shed"]


@pytest.mark.asyncio
async def test_a_publish_that_fails_serves_the_clone_and_gives_the_claim_back(
    tmp_path, git_http, make_origin, emitted
):
    bed, origin, old = await _bed(tmp_path, git_http, make_origin)
    origin.commit("master")
    bed.leader.fail = True

    r = await _get(bed)

    assert r.status_code == 200, r.text
    assert r.json()["hash"] == old
    assert _outcomes(emitted) == ["published_failed"]
    assert "live" not in scopes_api._fresh_fetch_claims


@pytest.mark.asyncio
async def test_a_client_that_hangs_up_ends_the_wait(
    tmp_path, git_http, make_origin, emitted
):
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    fetcher = GitPolicyFetcher(tmp_path, "live", bed.scope.policy)

    class _Gone:
        async def is_disconnected(self):
            return True

    outcome = await scopes_api._fresh_fetch_wait(
        fetcher,
        bed.clone,
        "live",
        _Gone(),
        lambda: bed.leader.publish(opal_server_config.POLICY_REPO_WEBHOOK_TOPIC, _SYNC),
    )

    assert outcome == "disconnected"
    assert _outcomes(emitted) == ["disconnected"]


@pytest.mark.parametrize(
    "configured, used", [(100.0, 55.0), (math.inf, 0.0), (10.0, 10.0)]
)
def test_the_wait_is_clamped_like_the_clone_wait(configured, used, monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS", configured
    )
    assert scopes_api._bounded_fresh_fetch_wait() == used


def test_the_wait_defaults_to_10_seconds():
    unset = OpalServerConfig(prefix="OPAL_UNSET_FOR_DEFAULTS_")
    assert unset.SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS == 10.0


# --- the marks the wait reads -------------------------------------------------------


def test_fetch_mark_after_reads_the_branch_all_and_failed_marks(tmp_path):
    marks = tmp_path / ".git" / "opal-fetched"
    marks.parent.mkdir()
    t = time.time()
    assert fetch_mark_after(tmp_path, "b", t) is None
    git_fetcher._write_fetch_marks(marks, ["FAILED"], t + 1)
    assert fetch_mark_after(tmp_path, "b", t) is False
    git_fetcher._write_fetch_marks(marks, [git_fetcher._fetch_mark_name("b")], t + 1)
    assert fetch_mark_after(tmp_path, "b", t) is True
    assert fetch_mark_after(tmp_path, "other", t) is False
    git_fetcher._write_fetch_marks(marks, ["ALL"], t + 1)
    assert fetch_mark_after(tmp_path, "other", t) is True
    assert fetch_mark_after(tmp_path, "other", t + 1) is None
    assert fetch_mark_after(tmp_path / "no-clone", "b", t) is None


@pytest.mark.asyncio
async def test_a_sync_skipped_for_backoff_writes_the_failed_mark(
    tmp_path, git_http, make_origin, monkeypatch
):
    """Its request's wait ends at once instead of at its end."""
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    fetcher = GitPolicyFetcher(tmp_path, "live", bed.scope.policy)
    fetcher._record_source_failure(RuntimeError("down"))
    before = time.time() - 0.001

    await fetcher.fetch_and_notify_on_changes(force_fetch=True, honor_backoff=True)

    assert fetch_mark_after(bed.clone, "master", before) is False


@pytest.mark.asyncio
async def test_a_sync_that_finds_the_backoff_under_the_lock_writes_the_failed_mark(
    tmp_path, git_http, make_origin, monkeypatch
):
    """The backoff a sync that waited for the clone's lock finds there, once
    another sync's fetch failed."""
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    fetcher = GitPolicyFetcher(tmp_path, "live", bed.scope.policy)
    fetcher._record_source_failure(RuntimeError("down"))
    entry = GitPolicyFetcher.source_backoff[fetcher.clone_source_id]
    looks = iter([None, entry])
    monkeypatch.setattr(fetcher, "_backoff_entry", lambda: next(looks))
    before = time.time() - 0.001

    await fetcher.fetch_and_notify_on_changes(force_fetch=True, honor_backoff=True)

    assert fetch_mark_after(bed.clone, "master", before) is False


@pytest.mark.asyncio
async def test_a_sync_skipped_for_backoff_on_a_source_with_no_clone_writes_nothing(
    tmp_path, git_http, make_origin, records
):
    make_origin(git_http.root / "repo.git")
    bed = _Bed(tmp_path, git_http.url("repo.git"), "master")
    fetcher = GitPolicyFetcher(tmp_path, "live", bed.scope.policy)
    fetcher._record_source_failure(RuntimeError("down"))

    await fetcher.fetch_and_notify_on_changes(force_fetch=True, honor_backoff=True)

    assert not bed.clone.exists()
    assert not [r for r in records if "Could not record" in r["message"]]


@pytest.mark.asyncio
async def test_a_pass_s_sync_skipped_for_backoff_writes_no_mark(
    tmp_path, git_http, make_origin
):
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    fetcher = GitPolicyFetcher(tmp_path, "live", bed.scope.policy)
    fetcher._record_source_failure(RuntimeError("down"))
    before = time.time() - 0.001

    with GitPolicyFetcher.sync_pass():
        await fetcher.fetch_and_notify_on_changes(force_fetch=True, honor_backoff=True)

    assert fetch_mark_after(bed.clone, "master", before) is None


@pytest.mark.asyncio
async def test_a_sync_that_gives_up_behind_a_running_op_writes_the_failed_mark(
    tmp_path, git_http, make_origin, monkeypatch
):
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    fetcher = GitPolicyFetcher(tmp_path, "live", bed.scope.policy)
    monkeypatch.setattr(git_fetcher, "git_op_in_flight", lambda key: True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0)
    before = time.time() - 0.001

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert fetch_mark_after(bed.clone, "master", before) is False


@pytest.mark.asyncio
async def test_a_sync_whose_wait_for_a_running_op_runs_out_writes_the_failed_mark(
    tmp_path, git_http, make_origin, monkeypatch
):
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    fetcher = GitPolicyFetcher(tmp_path, "live", bed.scope.policy)
    monkeypatch.setattr(git_fetcher, "git_op_in_flight", lambda key: True)

    async def never_gone(key, timeout):
        return False

    monkeypatch.setattr(git_fetcher, "wait_for_git_op_gone", never_gone)
    before = time.time() - 0.001

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert fetch_mark_after(bed.clone, "master", before) is False


@pytest.mark.fetch_backend("libgit2")
@pytest.mark.asyncio
async def test_libgit2_writes_no_mark_for_a_skipped_sync(
    tmp_path, git_http, make_origin
):
    bed, _, _ = await _bed(tmp_path, git_http, make_origin)
    fetcher = GitPolicyFetcher(tmp_path, "live", bed.scope.policy)
    fetcher._record_source_failure(RuntimeError("down"))

    await fetcher.fetch_and_notify_on_changes(force_fetch=True, honor_backoff=True)

    assert not (bed.clone / ".git" / "opal-fetched").exists()
