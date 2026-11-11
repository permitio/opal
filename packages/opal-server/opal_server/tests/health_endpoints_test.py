"""The server's health routes, as a Kubernetes probe reads them.

/healthz/live (liveness) fails only on this worker's broadcaster reader
having given up and on a scopes leader that stopped writing its
heartbeat; /healthz/started (startup) turns 200 once and stays there;
/healthcheck (readiness) also covers the WebSocket pub/sub route and, in
scopes mode, the worker's own backbone subscription. None of them reads
a git remote, Redis or the backbone.
"""
import asyncio
import dataclasses
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
from opal_common.config import opal_common_config
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server import git_cli
from opal_server import git_fetcher as git_fetcher_module
from opal_server import health
from opal_server import server as server_module
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, cli_ops_past_bound
from opal_server.health import HEARTBEAT_FILE_NAME, LeaderHeartbeat
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from opal_server.scopes.readiness import required_clones
from opal_server.server import OpalServer
from starlette.routing import Match
from starlette.testclient import TestClient

pytestmark = [
    # The routes read the clones a scope fetch makes with the git command line.
    pytest.mark.fetch_backend("cli"),
    # server.py registers its startup and shutdown callbacks with on_event,
    # which FastAPI deprecates; building a server here is not what is tested.
    pytest.mark.filterwarnings(r"ignore:\s*on_event is deprecated:DeprecationWarning"),
]

_REQUIRED = "https://git.example.com/org/policy.git"


@pytest.fixture(scope="module")
def scopes_server(tmp_path_factory):
    """A scopes server with the watcher, the publisher and a reconnecting
    broadcaster: one whose leader writes a heartbeat and whose workers each
    hold a backbone subscription. Built once; nothing here connects."""
    saved = {
        key: getattr(opal_server_config, key)
        for key in ("SCOPES", "REDIS_URL", "LEADER_LOCK_FILE_PATH", "BASE_DIR")
    }
    base = tmp_path_factory.mktemp("scopes-server")
    opal_server_config.SCOPES = True
    opal_server_config.REDIS_URL = "redis://localhost:1"
    opal_server_config.LEADER_LOCK_FILE_PATH = str(base / "leader.lock")
    opal_server_config.BASE_DIR = str(base)
    try:
        return OpalServer(
            init_policy_watcher=True,
            broadcaster_uri="postgres://localhost:1/backbone",
            enable_jwks_endpoint=False,
        )
    finally:
        for key, value in saved.items():
            setattr(opal_server_config, key, value)


@pytest.fixture(scope="module")
def plain_server():
    """A server with no scopes and no broadcaster, whose leader watches a
    single policy repository (the watcher on, as by default)."""
    scopes = opal_server_config.SCOPES
    opal_server_config.SCOPES = False
    try:
        return OpalServer(
            init_policy_watcher=True, broadcaster_uri=None, enable_jwks_endpoint=False
        )
    finally:
        opal_server_config.SCOPES = scopes


def _fresh_health(server):
    server.health = dataclasses.replace(
        server.health, started_at=None, backbone_subscribed=None, startup_passed=False
    )


@pytest.fixture
def scopes(scopes_server, monkeypatch, tmp_path):
    """The scopes server as a worker that has just started (its background task
    not run yet), with a BASE_DIR of the test's own, an idle healthy
    broadcaster and a latch that has seen nothing."""
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [])
    monkeypatch.setattr(opal_server_config, "BROADCAST_HEALTHCHECK_ENABLED", True)
    monkeypatch.setattr(required_clones, "_landed", set())
    monkeypatch.setattr(scopes_server, "health", scopes_server.health)
    monkeypatch.setattr(
        scopes_server.pubsub, "broadcaster", _broadcaster(scopes_server)
    )
    _fresh_health(scopes_server)
    return scopes_server


@pytest.fixture
def plain(plain_server, monkeypatch, tmp_path):
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(plain_server, "health", plain_server.health)
    _fresh_health(plain_server)
    return plain_server


def _broadcaster(server, listeners=0, reader=None):
    broadcaster = ReconnectingBroadcaster(
        "memory://", notifier=server.pubsub.notifier, channel="test"
    )
    broadcaster._listen_count = listeners
    broadcaster._subscription_task = reader
    return broadcaster


class _Reader:
    """Stands in for the reader task: pending (mid-reconnect included) or
    done (gave up or died)."""

    def __init__(self, done: bool) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done


def _gave_up(server):
    server.pubsub.broadcaster = _broadcaster(server, listeners=1, reader=_Reader(True))


def _reconnecting(server):
    server.pubsub.broadcaster = _broadcaster(server, listeners=1, reader=_Reader(False))


def _heartbeat(base: Path, at: float) -> Path:
    path = base / HEARTBEAT_FILE_NAME
    path.write_text(
        json.dumps({"pid": 1, "at": at, "last_attempt_at": None, "last_attempt": None})
    )
    return path


def _started(server, at=None):
    server.health.started_at = time.time() if at is None else at


def _get(server, path):
    return TestClient(server.app).get(path)


def _landed(base: Path, url: str) -> None:
    git_dir = GitPolicyFetcher.base_dir(base) / f"{GitPolicyFetcher.repo_hash(url)}-0"
    (git_dir / ".git").mkdir(parents=True)
    (git_dir / ".git" / "packed-refs").write_text("# pack-refs with: peeled\n")


# --- /healthz/live ------------------------------------------------------------


@pytest.fixture
def no_network(monkeypatch):
    """Any connection or child process raises: a route that needs one fails."""

    def _refuse(*args, **kwargs):
        raise AssertionError("a health route tried to reach the network or run git")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(subprocess, "Popen", _refuse)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _refuse)


def test_live_is_200_with_no_remote_no_redis_and_the_backbone_reconnecting(
    scopes, tmp_path, no_network
):
    _reconnecting(scopes)
    _heartbeat(tmp_path, time.time())
    response = _get(scopes, "/healthz/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_live_is_503_when_the_leader_heartbeat_is_older_than_300s(scopes, tmp_path):
    _heartbeat(tmp_path, time.time() - 301)
    response = _get(scopes, "/healthz/live")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["leader"]}


def test_live_is_200_with_a_heartbeat_just_under_300s(scopes, tmp_path):
    _heartbeat(tmp_path, time.time() - 290)
    assert _get(scopes, "/healthz/live").status_code == 200


def test_live_is_503_without_a_heartbeat_file(scopes):
    response = _get(scopes, "/healthz/live")
    assert response.status_code == 503
    assert response.json()["failed"] == ["leader"]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{not json",
        "[]",
        '{"pid": 1}',
        '{"at": "soon"}',
        '{"at": null}',
        '{"at": true}',
    ],
)
def test_live_reads_a_heartbeat_it_cannot_parse_as_none(scopes, tmp_path, content):
    (tmp_path / HEARTBEAT_FILE_NAME).write_text(content)
    assert _get(scopes, "/healthz/live").json()["failed"] == ["leader"]


def test_live_reads_the_heartbeat_in_base_dir_not_in_git_sources(scopes, tmp_path):
    clones = GitPolicyFetcher.base_dir(tmp_path)
    clones.mkdir()
    _heartbeat(clones, time.time())
    assert _get(scopes, "/healthz/live").json()["failed"] == ["leader"]


def test_live_is_503_when_the_reader_gave_up(scopes, tmp_path):
    _heartbeat(tmp_path, time.time())
    _gave_up(scopes)
    response = _get(scopes, "/healthz/live")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["broadcaster"]}


def test_live_leaves_the_reader_to_the_kill_switch(scopes, tmp_path, monkeypatch):
    _heartbeat(tmp_path, time.time())
    _gave_up(scopes)
    monkeypatch.setattr(opal_server_config, "BROADCAST_HEALTHCHECK_ENABLED", False)
    assert _get(scopes, "/healthz/live").status_code == 200


def test_live_names_every_failure(scopes):
    _gave_up(scopes)
    assert _get(scopes, "/healthz/live").json()["failed"] == ["broadcaster", "leader"]


def test_live_ignores_the_leader_without_scopes(plain):
    response = _get(plain, "/healthz/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "watcher, publisher",
    [(False, True), (True, False)],
    ids=["no-watcher", "no-publisher"],
)
def test_live_ignores_the_leader_when_no_worker_runs_the_watcher(
    monkeypatch, tmp_path, watcher, publisher
):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "REDIS_URL", "redis://localhost:1")
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    server = OpalServer(
        init_policy_watcher=watcher,
        init_publisher=publisher,
        broadcaster_uri="postgres://localhost:1/backbone",
        enable_jwks_endpoint=False,
    )
    assert server.health.expects_scopes_leader is False
    assert server.health.expects_backbone_subscription is publisher
    assert _get(server, "/healthz/live").status_code == 200
    assert _get(server, "/healthz/started").status_code == 503
    _started(server)
    assert _get(server, "/healthz/started").status_code == 200


# --- /healthz/started ---------------------------------------------------------


def test_started_waits_for_the_worker_then_for_a_heartbeat_after_it(scopes, tmp_path):
    response = _get(scopes, "/healthz/started")
    assert response.status_code == 503
    assert response.json() == {
        "status": "starting",
        "waiting_for": ["worker", "leader"],
    }

    _started(scopes)
    _heartbeat(tmp_path, scopes.health.started_at - 5)
    assert _get(scopes, "/healthz/started").json()["waiting_for"] == ["leader"]

    _heartbeat(tmp_path, scopes.health.started_at + 0.5)
    response = _get(scopes, "/healthz/started")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_started_waits_for_required_clones_then_stays_200(
    scopes, tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [_REQUIRED])
    _started(scopes)
    _heartbeat(tmp_path, time.time() + 1)
    response = _get(scopes, "/healthz/started")
    assert response.status_code == 503
    assert response.json()["waiting_for"] == ["clones"]

    _landed(tmp_path, _REQUIRED)
    assert _get(scopes, "/healthz/started").status_code == 200

    # Started once, started for good: the clone gone, the heartbeat stale.
    for path in sorted(GitPolicyFetcher.base_dir(tmp_path).rglob("*"), reverse=True):
        path.rmdir() if path.is_dir() else path.unlink()
    _heartbeat(tmp_path, time.time() - 3600)
    _gave_up(scopes)
    assert _get(scopes, "/healthz/started").status_code == 200


def test_started_names_the_clones_with_the_rest(scopes, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [_REQUIRED])
    assert _get(scopes, "/healthz/started").json()["waiting_for"] == [
        "worker",
        "leader",
        "clones",
    ]


def test_started_without_scopes_waits_only_for_the_worker(plain):
    assert _get(plain, "/healthz/started").json()["waiting_for"] == ["worker"]
    _started(plain)
    assert _get(plain, "/healthz/started").status_code == 200


def test_started_never_carries_a_url(scopes, monkeypatch):
    secret = "https://user:hunter2@git.example.com/org/policy.git"
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [secret])
    assert "hunter2" not in _get(scopes, "/healthz/started").text


# --- /healthcheck -------------------------------------------------------------


def test_readiness_is_503_until_the_backbone_subscription_started(scopes):
    response = _get(scopes, "/healthcheck")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "pubsub": "no backbone subscription"}
    scopes.health.backbone_subscribed = True
    assert _get(scopes, "/healthcheck").json() == {"status": "ok"}


def test_readiness_is_503_without_a_backbone_subscription(scopes):
    scopes.health.backbone_subscribed = False
    assert _get(scopes, "/healthcheck").json() == {
        "status": "error",
        "pubsub": "no backbone subscription",
    }


def test_readiness_leaves_the_subscription_to_the_kill_switch(scopes, monkeypatch):
    scopes.health.backbone_subscribed = False
    monkeypatch.setattr(opal_server_config, "BROADCAST_HEALTHCHECK_ENABLED", False)
    assert _get(scopes, "/healthcheck").status_code == 200


def test_readiness_stays_200_through_a_backbone_reconnect(scopes):
    scopes.health.backbone_subscribed = True
    _reconnecting(scopes)
    assert _get(scopes, "/healthcheck").status_code == 200


def test_readiness_wants_no_subscription_without_scopes(plain):
    assert _get(plain, "/healthcheck").status_code == 200


def test_the_broadcaster_503_still_comes_first(scopes):
    _gave_up(scopes)
    assert _get(scopes, "/healthcheck").json() == {
        "status": "error",
        "broadcaster": "unhealthy",
    }


def test_the_subscription_503_comes_before_the_clones(scopes, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [_REQUIRED])
    assert _get(scopes, "/healthcheck").json()["pubsub"] == "no backbone subscription"
    scopes.health.backbone_subscribed = True
    assert _get(scopes, "/healthcheck").json()["scopes"] == "clones missing"


def test_readiness_is_503_without_the_ws_route(plain, monkeypatch):
    ws = {"type": "websocket", "path": "/ws", "root_path": "", "headers": []}
    routes = [
        route for route in plain.app.router.routes if route.matches(ws)[0] != Match.FULL
    ]
    assert len(routes) == len(plain.app.router.routes) - 1, "no /ws route to remove"
    monkeypatch.setattr(plain.app.router, "routes", routes)
    response = _get(plain, "/healthcheck")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "pubsub": "not mounted"}


# --- what the worker's start records ------------------------------------------


class _Publisher:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Context:
    """The worker's global listening context; raises on enter when told to,
    after counting the listener as the library does."""

    def __init__(self, fail: bool) -> None:
        self._fail = fail
        self.listen_count = 0

    async def __aenter__(self):
        self.listen_count += 1
        if self._fail:
            raise ConnectionRefusedError("backbone refused")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.listen_count -= 1


class _NeverGranted:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        await asyncio.Event().wait()

    async def __aexit__(self, *exc):
        return False


async def _start_worker(server, monkeypatch, context):
    """Run the worker's background task up to the leadership lock, which never
    comes (a non-leader worker)."""
    monkeypatch.setattr(server_module, "NamedLock", _NeverGranted)

    async def _subscribe(endpoint):
        return None

    monkeypatch.setattr(server_module, "subscribe_worker_purge_handler", _subscribe)
    monkeypatch.setattr(server, "publisher", _Publisher())
    monkeypatch.setattr(server, "opal_statistics", None)
    monkeypatch.setattr(server, "broadcast_listening_context", context)
    task = asyncio.create_task(server.start_server_background_tasks())
    for _ in range(1000):
        if server.health.started_at is not None:
            break
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_worker_that_entered_its_listening_context_is_ready(
    scopes, monkeypatch, tmp_path
):
    before = time.time()
    await _start_worker(scopes, monkeypatch, _Context(fail=False))
    assert scopes.health.backbone_subscribed is True
    assert before <= scopes.health.started_at <= time.time()
    assert _get(scopes, "/healthcheck").status_code == 200


@pytest.mark.asyncio
async def test_a_worker_whose_listening_context_failed_is_not_ready(
    scopes, monkeypatch
):
    await _start_worker(scopes, monkeypatch, _Context(fail=True))
    assert scopes.health.backbone_subscribed is False
    assert scopes.health.started_at is not None
    assert _get(scopes, "/healthcheck").json()["pubsub"] == "no backbone subscription"


@pytest.mark.asyncio
async def test_a_worker_with_no_publisher_has_started_at_once(plain, monkeypatch):
    monkeypatch.setattr(plain, "publisher", None)
    await plain.start_server_background_tasks()
    assert plain.health.started_at is not None
    assert _get(plain, "/healthz/started").status_code == 200


def test_a_server_wants_a_backbone_subscription_only_with_scopes_and_a_reader(
    scopes, plain
):
    assert scopes.health.expects_backbone_subscription is True
    assert scopes.health.expects_scopes_leader is True
    assert plain.health.expects_backbone_subscription is False
    assert plain.health.expects_scopes_leader is False


def test_root_still_answers_200_whatever_the_probes_say(scopes):
    _gave_up(scopes)
    assert _get(scopes, "/").status_code == 200


def test_statistics_alone_do_not_ask_for_a_backbone_subscription(monkeypatch, tmp_path):
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    monkeypatch.setattr(opal_common_config, "STATISTICS_ENABLED", True)
    server = OpalServer(
        init_policy_watcher=False,
        broadcaster_uri="postgres://localhost:1/backbone",
        enable_jwks_endpoint=False,
    )
    assert server.broadcast_listening_context is not None
    assert server.health.expects_backbone_subscription is False
    assert _get(server, "/healthcheck").status_code == 200


def test_the_heartbeat_file_name_is_not_a_source_id():
    from opal_server.git_fetcher import SOURCE_ID_RE

    assert not SOURCE_ID_RE.match(HEARTBEAT_FILE_NAME)
    assert os.sep not in HEARTBEAT_FILE_NAME


# --- no git op ages the heartbeat; a wedged leader loop does ------------------


@pytest.fixture
def quick_heartbeat(monkeypatch):
    """A heartbeat every 0.05 s that /healthz/live finds too old at 0.5 s."""
    monkeypatch.setattr(health, "_HEARTBEAT_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(health, "_LEADER_HEARTBEAT_MAX_AGE", 0.5)


@pytest.fixture
def stalled_clone(git_http, make_origin, tmp_path, monkeypatch):
    """A scope fetcher whose first sync is a git command-line clone that the
    server stalls mid-pack until released; bounds with no kill grace and no
    slack, so that a bound from anything shorter than the clone's own timeout
    would hold the heartbeat."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.0)
    monkeypatch.setattr(git_cli, "KILL_WAIT_SECONDS", 0.5)
    monkeypatch.setattr(git_fetcher_module, "_CLI_OP_BOUND_SLACK_SECONDS", 0.0)
    caches = (
        GitPolicyFetcher.repos,
        GitPolicyFetcher.repos_last_fetched,
        GitPolicyFetcher.repo_locks,
        GitPolicyFetcher.source_backoff,
        GitPolicyFetcher.pending_branches,
        GitPolicyFetcher.branch_attempts,
        GitPolicyFetcher.fetch_failures,
    )
    for cache in caches:
        cache.clear()
    origin = make_origin(git_http.root / "repo.git")
    origin.commit("master", {"big.bin": os.urandom(2 * 1024 * 1024)})
    git_http.stall_after = 1024
    source = GitPolicyScopeSource(
        source_type="git",
        url=git_http.url("repo.git"),
        branch="master",
        auth=NoAuthData(auth_type="none"),
    )
    yield GitPolicyFetcher(tmp_path, "scope", source)
    git_http.release.set()
    for cache in caches:
        cache.clear()


async def _first_beat(base: Path) -> None:
    for _ in range(200):
        if (base / HEARTBEAT_FILE_NAME).exists():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the leader never wrote its heartbeat")


async def _live_while(server, task, seconds):
    """GET /healthz/live every 0.1 s for ``seconds`` while ``task`` runs, off
    the event loop the heartbeat beats on; the status codes."""
    client = TestClient(server.app)
    answers = []
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        answers.append(
            (await asyncio.to_thread(client.get, "/healthz/live")).status_code
        )
        await asyncio.sleep(0.1)
    assert not task.done(), "the git op ended before the probes: nothing measured"
    return answers


@pytest.mark.asyncio
async def test_a_clone_running_up_to_its_timeout_keeps_live_200(
    scopes, tmp_path, quick_heartbeat, stalled_clone, git_http, monkeypatch
):
    """The clone runs 2.3 s of its 4 s timeout: longer than the heartbeat's
    limit (0.5 s) and than the fetch timeout plus the kill wait (0.7 s), so a
    bound from the fetch timeout would fail /healthz/live at about 1.2 s."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.2)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", 4.0)
    beating = asyncio.create_task(LeaderHeartbeat().run())
    await _first_beat(tmp_path)
    clone = asyncio.create_task(stalled_clone.fetch_and_notify_on_changes())
    try:
        answers = await _live_while(scopes, clone, 2.3)
        assert git_http.stalled.is_set()
    finally:
        git_http.release.set()
        await clone
        beating.cancel()
        await asyncio.gather(beating, return_exceptions=True)
    assert set(answers) == {200}, answers


@pytest.mark.asyncio
async def test_a_clone_with_no_timeout_never_holds_the_heartbeat(
    scopes, tmp_path, quick_heartbeat, stalled_clone, git_http, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", 0.0)
    beating = asyncio.create_task(LeaderHeartbeat().run())
    await _first_beat(tmp_path)
    clone = asyncio.create_task(stalled_clone.fetch_and_notify_on_changes())
    try:
        answers = await _live_while(scopes, clone, 1.5)
        assert git_http.stalled.is_set()
        assert cli_ops_past_bound(now=time.monotonic() + 10**9) == 0
    finally:
        git_http.release.set()
        await clone
        beating.cancel()
        await asyncio.gather(beating, return_exceptions=True)
    assert set(answers) == {200}, answers


def test_a_wedged_leader_loop_fails_live_once_its_heartbeat_is_too_old(
    scopes, tmp_path, quick_heartbeat
):
    """The leader's event loop, on a thread of its own, blocks for 2.0 s; this
    worker answers from its own."""
    wedge = threading.Event()
    done = threading.Event()

    async def _leader():
        beating = asyncio.create_task(LeaderHeartbeat().run())
        while not done.is_set():
            if wedge.is_set():
                wedge.clear()
                time.sleep(2.0)
            await asyncio.sleep(0.01)
        beating.cancel()
        await asyncio.gather(beating, return_exceptions=True)

    leader = threading.Thread(target=asyncio.run, args=(_leader(),))
    leader.start()
    try:
        for _ in range(200):
            if (tmp_path / HEARTBEAT_FILE_NAME).exists():
                break
            time.sleep(0.01)
        assert _get(scopes, "/healthz/live").status_code == 200
        wedge.set()
        wedged = time.monotonic()
        time.sleep(1.0)
        response = _get(scopes, "/healthz/live")
        assert response.status_code == 503
        assert response.json()["failed"] == ["leader"]
        time.sleep(max(0.0, wedged + 2.6 - time.monotonic()))
        assert _get(scopes, "/healthz/live").status_code == 200
    finally:
        done.set()
        leader.join()


# --- the heartbeat starts with the leadership lock, before Redis --------------


class _GrantedLock:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Watcher:
    """The scopes watcher: entered once the scopes are loaded."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()

    async def __aenter__(self):
        self.entered.set()
        return self

    async def __aexit__(self, *exc):
        return False

    async def wait_until_should_stop(self):
        await asyncio.Event().wait()


class _Redis:
    """The scope store: refuses or hangs until ``back`` is set."""

    def __init__(self, how: str) -> None:
        self._how = how
        self.back = asyncio.Event()
        self.attempts = 0
        self.stored = []

    async def put(self, scope):
        self.attempts += 1
        if not self.back.is_set():
            if self._how == "refuses":
                from redis.exceptions import ConnectionError as RedisConnectionError

                raise RedisConnectionError("Error 111 connecting to localhost:6379.")
            await self.back.wait()
        self.stored.append(scope)


@pytest.fixture
def leader(scopes, monkeypatch, quick_heartbeat):
    """The scopes server as the worker that wins the leadership lock, with
    OPAL_POLICY_REPO_URL set (its election stores the default scope in Redis)
    and quick retries of that store."""
    from opal_server.scopes import loader as loader_module

    monkeypatch.setattr(opal_server_config, "POLICY_REPO_URL", _REQUIRED)
    monkeypatch.setattr(loader_module, "_STORE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(loader_module, "_RETRY_MIN_SECONDS", 0.01)
    monkeypatch.setattr(loader_module, "_RETRY_MAX_SECONDS", 0.02)
    monkeypatch.setattr(server_module, "NamedLock", _GrantedLock)

    async def _subscribe(endpoint):
        return None

    monkeypatch.setattr(server_module, "subscribe_worker_purge_handler", _subscribe)
    watcher = _Watcher()
    monkeypatch.setattr(server_module, "setup_watcher_task", lambda *a: watcher)
    monkeypatch.setattr(scopes, "publisher", _Publisher())
    monkeypatch.setattr(scopes, "opal_statistics", None)
    monkeypatch.setattr(scopes, "broadcast_keepalive", None)
    monkeypatch.setattr(scopes, "broadcast_listening_context", _Context(fail=False))
    monkeypatch.setattr(scopes, "_graceful_shutdown", lambda: None)
    scopes.test_watcher = watcher
    yield scopes
    del scopes.test_watcher


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["refuses", "hangs"])
async def test_a_redis_down_at_election_never_fails_live_or_startup(
    leader, tmp_path, monkeypatch, how
):
    redis = _Redis(how)
    monkeypatch.setattr(leader, "_scopes", redis)
    errors = []
    from opal_server.scopes import loader as loader_module

    monkeypatch.setattr(
        loader_module.logger, "error", lambda m, *a, **k: errors.append(k)
    )
    running = asyncio.create_task(leader.start_server_background_tasks())
    try:
        await _first_beat(tmp_path)
        answers = await _live_while(leader, running, 1.2)
        started = await asyncio.to_thread(
            TestClient(leader.app).get, "/healthz/started"
        )
        assert set(answers) == {200}, answers
        assert started.status_code == 200, started.json()
        assert redis.attempts >= 3 and len(errors) >= 2
        assert not leader.test_watcher.entered.is_set()

        redis.back.set()
        await asyncio.wait_for(leader.test_watcher.entered.wait(), timeout=5)
        assert [scope.policy.url for scope in redis.stored] == [_REQUIRED]
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
    stopped = json.loads((tmp_path / HEARTBEAT_FILE_NAME).read_text())["at"]
    await asyncio.sleep(0.2)
    assert json.loads((tmp_path / HEARTBEAT_FILE_NAME).read_text())["at"] == stopped


@pytest.mark.asyncio
async def test_the_heartbeat_ends_when_the_leader_leaves_the_lock(
    leader, tmp_path, monkeypatch
):
    class _Broken:
        async def put(self, scope):
            # Within the store's time limit (0.05 s), after the first beat.
            await asyncio.sleep(0.03)
            raise ValueError("the default scope cannot be stored")

    monkeypatch.setattr(leader, "_scopes", _Broken())
    with pytest.raises(ValueError):
        await asyncio.wait_for(leader.start_server_background_tasks(), timeout=5)
    stopped = json.loads((tmp_path / HEARTBEAT_FILE_NAME).read_text())["at"]
    await asyncio.sleep(0.2)
    assert json.loads((tmp_path / HEARTBEAT_FILE_NAME).read_text())["at"] == stopped


@pytest.mark.asyncio
async def test_a_leader_with_no_watcher_writes_no_heartbeat(
    plain, tmp_path, monkeypatch, quick_heartbeat
):
    class _Keepalive:
        """A leader with no watcher holds the lock on the keepalive."""

        def start(self):
            return None

        async def wait_until_done(self):
            await asyncio.sleep(0.3)

    monkeypatch.setattr(server_module, "NamedLock", _GrantedLock)
    monkeypatch.setattr(plain, "publisher", _Publisher())
    monkeypatch.setattr(plain, "opal_statistics", None)
    monkeypatch.setattr(plain, "broadcast_keepalive", _Keepalive())
    monkeypatch.setattr(plain, "_init_policy_watcher", False)
    await asyncio.wait_for(plain.start_server_background_tasks(), timeout=5)
    assert not (tmp_path / HEARTBEAT_FILE_NAME).exists()
