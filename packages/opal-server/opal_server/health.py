"""The server's health routes, and the scopes leader's heartbeat they read.

- ``GET /healthz/live``, for a liveness probe: 503 when this worker's
  broadcaster reader gave up or died, or, in scopes mode, when the pod's
  scopes leader stopped writing its heartbeat.
- ``GET /healthz/started``, for a startup probe: 200 once this worker has
  started, the leader has written a heartbeat since, and every clone of
  SCOPES_READY_REQUIRED_REPOS has landed; 200 from then on.
- ``GET /healthcheck``, for a readiness probe: the broadcaster reader, the
  WebSocket pub/sub route, in scopes mode the worker's own backbone
  subscription, and the required clones.

Each route is a sync handler that reads attributes and local files only:
no git remote, no Redis, no backbone, no lock.
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_server.config import opal_server_config
from opal_server.git_fetcher import SOURCE_ID_RE, GitPolicyFetcher, cli_ops_past_bound
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from opal_server.scopes.readiness import required_clones
from starlette.routing import Match

if TYPE_CHECKING:
    from opal_server.server import OpalServer

# In BASE_DIR, outside git_sources, so nothing that manages the clones
# touches it.
HEARTBEAT_FILE_NAME = "scopes-leader.heartbeat"
_HEARTBEAT_INTERVAL_SECONDS = 10.0
# The fetch metrics go with every third beat: every 30 seconds.
_FETCH_METRICS_EVERY_BEATS = 3
# Older than this, the heartbeat fails /healthz/live. It covers a leader
# re-election (the leadership lock is retried every 5 seconds) and a worker
# restart.
_LEADER_HEARTBEAT_MAX_AGE = 300.0
# A WebSocket connection to the pub/sub route (pubsub.py), as the app's
# routes match one.
_PUBSUB_SCOPE = {
    "type": "websocket",
    "path": "/ws",
    "root_path": "",
    "headers": [],
    "query_string": b"",
}


@dataclass
class WorkerHealth:
    """What this worker's health routes read besides the heartbeat file.

    Attributes:
        expects_scopes_leader: Scopes mode with the watcher and the
            publisher on: some worker of the pod leads and writes the
            heartbeat.
        expects_backbone_subscription: Scopes mode with the reconnecting
            broadcaster and the publisher on: this worker holds a backbone
            subscription of its own.
        started_at: When this worker's start finished (epoch seconds).
        backbone_subscribed: True once the subscription started, False when
            it failed to, None before.
        startup_passed: /healthz/started has answered 200.
    """

    expects_scopes_leader: bool = False
    expects_backbone_subscription: bool = False
    started_at: Optional[float] = None
    backbone_subscribed: Optional[bool] = None
    startup_passed: bool = False


def heartbeat_path(base_dir: Path) -> Path:
    return base_dir / HEARTBEAT_FILE_NAME


def read_heartbeat_at(base_dir: Path) -> Optional[float]:
    """When the scopes leader last wrote its heartbeat (epoch seconds); None
    when there is none, or none that can be read."""
    path = heartbeat_path(base_dir)
    try:
        beat = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        logger.warning(
            "Could not read the scopes leader heartbeat {path}: {err!r}",
            path=str(path),
            err=e,
        )
        return None
    at = beat.get("at") if isinstance(beat, dict) else None
    if not isinstance(at, (int, float)):
        logger.warning(
            "The scopes leader heartbeat {path} holds no time", path=str(path)
        )
        return None
    return float(at)


class LeaderHeartbeat:
    """The scopes leader's heartbeat: a file in BASE_DIR that every worker of
    the pod reads for /healthz/live and /healthz/started.

    The leader runs ``run()`` while it holds the leadership lock
    (running_leader_heartbeat). Each beat sends
    ``opal_server.scopes.leader`` and writes the file, unless a git
    command-line op is still awaited past its bound (cli_ops_past_bound):
    then the leader cannot sync, and the heartbeat ages until the op ends
    or liveness restarts the pod. Every third beat sends the fetch metrics.
    A libgit2 op whose awaiter timed out is not awaited any more, so it
    never holds the heartbeat.
    """

    def __init__(self) -> None:
        self._last_attempt_at: Optional[float] = None
        self._last_attempt: Optional[str] = None
        self._held = False
        self._write_failed = False

    def note_attempt(self, ok: bool) -> None:
        """Record a sync pass or scope refresh that ended, for the next beat.

        Args:
            ok: Whether it ended without raising.
        """
        self._last_attempt_at = time.time()
        self._last_attempt = "ok" if ok else "failed"

    async def run(self) -> None:
        """Beat now, then every 10 seconds, until cancelled."""
        logger.info(
            "Scopes leader heartbeat: writing {path} every {interval:.0f}s",
            path=str(heartbeat_path(Path(opal_server_config.BASE_DIR))),
            interval=_HEARTBEAT_INTERVAL_SECONDS,
        )
        number = 0
        while True:
            try:
                self.beat(number)
            except Exception:
                # The next beat tries again; a heartbeat task that died would
                # restart the pod through /healthz/live.
                logger.exception("Scopes leader heartbeat: the beat failed")
            number += 1
            await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)

    def beat(self, number: int) -> None:
        """One beat; the fetch metrics go with every third.

        Args:
            number: How many beats came before this one.
        """
        base_dir = Path(opal_server_config.BASE_DIR)
        metrics.gauge("opal_server.scopes.leader", 1)
        stuck = cli_ops_past_bound()
        if stuck:
            if not self._held:
                self._held = True
                logger.warning(
                    "Not writing the scopes leader heartbeat: {count} git "
                    "command-line op(s) still awaited past their timeout, "
                    "SCOPES_GIT_CLI_KILL_GRACE and 40 seconds more; "
                    "/healthz/live answers 503 once the heartbeat is {age:.0f}s old",
                    count=stuck,
                    age=_LEADER_HEARTBEAT_MAX_AGE,
                )
        else:
            if self._held:
                self._held = False
                logger.info(
                    "Writing the scopes leader heartbeat again: no git op is "
                    "past its bound"
                )
            self._write(base_dir)
        if number % _FETCH_METRICS_EVERY_BEATS == 0:
            try:
                emit_repo_fetch_metrics(base_dir)
            except Exception:
                logger.exception("Could not send the scope repository fetch metrics")

    def _write(self, base_dir: Path) -> None:
        path = heartbeat_path(base_dir)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        beat = {
            "pid": os.getpid(),
            "at": time.time(),
            "last_attempt_at": self._last_attempt_at,
            "last_attempt": self._last_attempt,
        }
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(beat))
            os.replace(temporary, path)
        except OSError as e:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup:
                logger.debug(
                    "Could not remove {path}: {err!r}", path=str(temporary), err=cleanup
                )
            log = logger.debug if self._write_failed else logger.warning
            self._write_failed = True
            log(
                "Could not write the scopes leader heartbeat {path}: {err!r}; "
                "/healthz/live answers 503 once the heartbeat is {age:.0f}s old",
                path=str(path),
                err=e,
                age=_LEADER_HEARTBEAT_MAX_AGE,
            )
            return
        if self._write_failed:
            self._write_failed = False
            logger.info(
                "Wrote the scopes leader heartbeat {path} again", path=str(path)
            )


# This process's heartbeat; only the scopes leader runs it.
leader_heartbeat = LeaderHeartbeat()


@asynccontextmanager
async def running_leader_heartbeat(enabled: bool) -> AsyncIterator[None]:
    """Run this process's heartbeat while the block runs, when ``enabled``.

    The leader enters it as soon as it holds the leadership lock, before it
    reads Redis or runs git, and leaves it with the lock.

    Args:
        enabled: Whether this server's leader writes a heartbeat
            (WorkerHealth.expects_scopes_leader).
    """
    if not enabled:
        yield
        return
    beating = asyncio.create_task(leader_heartbeat.run())
    try:
        yield
    finally:
        beating.cancel()
        await asyncio.gather(beating, return_exceptions=True)


def emit_repo_fetch_metrics(base_dir: Path) -> None:
    """Send each scope clone's fetch age and consecutive fetch failures.

    For each clone in BASE_DIR's git_sources, ``repo_fetch_age_seconds``
    is now minus its FETCH_HEAD's mtime (with the git command line, the
    last fetch or clone of it that succeeded); none for a clone with no
    FETCH_HEAD. ``repo_fetch_failures`` is its clones and fetches that
    failed in a row, sent also for a source whose clone never landed. Tags:
    ``repo``, the first 12 hex of the source id (the sha256 of the URL), and
    ``shard``; never a URL.

    Args:
        base_dir: BASE_DIR.
    """
    clones = GitPolicyFetcher.base_dir(base_dir)
    now = time.time()
    on_disk = set()
    try:
        with os.scandir(clones) as entries:
            for entry in entries:
                if SOURCE_ID_RE.match(entry.name) and entry.is_dir(
                    follow_symlinks=False
                ):
                    on_disk.add(entry.name)
    except FileNotFoundError:
        logger.debug("No scope clones yet in {path}", path=str(clones))
    failures: Dict[str, int] = dict(GitPolicyFetcher.fetch_failures)
    for source_id in sorted(on_disk | set(failures)):
        repo, _, shard = source_id.rpartition("-")
        tags = {"repo": repo[:12], "shard": shard}
        if source_id in on_disk:
            age = _fetch_head_age(clones / source_id / ".git" / "FETCH_HEAD", now)
            if age is not None:
                metrics.gauge("opal_server.scopes.repo_fetch_age_seconds", age, tags)
        metrics.gauge(
            "opal_server.scopes.repo_fetch_failures", failures.get(source_id, 0), tags
        )


def _fetch_head_age(fetch_head: Path, now: float) -> Optional[float]:
    try:
        mtime = os.stat(fetch_head).st_mtime
    except FileNotFoundError, NotADirectoryError:
        return None
    except OSError as e:
        logger.warning(
            "Could not read {path} for the fetch age metric: {err!r}",
            path=str(fetch_head),
            err=e,
        )
        return None
    return max(0.0, now - mtime)


def _reader_healthy(server: "OpalServer") -> bool:
    """False when this worker's reconnecting broadcaster reader gave up, died,
    or is missing while clients listen (is_reader_healthy)."""
    broadcaster = server.pubsub.broadcaster
    if not opal_server_config.BROADCAST_HEALTHCHECK_ENABLED or not isinstance(
        broadcaster, ReconnectingBroadcaster
    ):
        return True
    return broadcaster.is_reader_healthy()


def _pubsub_route_mounted(app: FastAPI) -> bool:
    """Whether a WebSocket connection to /ws reaches a route of ``app``."""
    return any(
        route.matches(_PUBSUB_SCOPE)[0] == Match.FULL for route in app.router.routes
    )


def register_health_routes(app: FastAPI, server: "OpalServer") -> None:
    """Mount /healthz/live, /healthz/started and /healthcheck on ``app``.

    Args:
        app: The server's app.
        server: The server; the routes read ``server.health`` and its
            broadcaster at each request.
    """

    @app.get("/healthz/live", include_in_schema=False)
    def healthz_live():
        failed: List[str] = []
        if not _reader_healthy(server):
            failed.append("broadcaster")
        if server.health.expects_scopes_leader:
            at = read_heartbeat_at(Path(opal_server_config.BASE_DIR))
            if at is None or time.time() - at > _LEADER_HEARTBEAT_MAX_AGE:
                failed.append("leader")
        if failed:
            return JSONResponse(
                status_code=503, content={"status": "error", "failed": failed}
            )
        return {"status": "ok"}

    @app.get("/healthz/started", include_in_schema=False)
    def healthz_started():
        health = server.health
        if health.startup_passed:
            return {"status": "ok"}
        base_dir = Path(opal_server_config.BASE_DIR)
        waiting: List[str] = []
        if health.started_at is None:
            waiting.append("worker")
        if health.expects_scopes_leader:
            at = read_heartbeat_at(base_dir)
            if health.started_at is None or at is None or at < health.started_at:
                waiting.append("leader")
        if required_clones.missing(base_dir):
            waiting.append("clones")
        if waiting:
            return JSONResponse(
                status_code=503, content={"status": "starting", "waiting_for": waiting}
            )
        health.startup_passed = True
        return {"status": "ok"}

    @app.get("/healthcheck", include_in_schema=False)
    def healthcheck():
        # Readiness: also reflect broadcaster-reader health so a wedged reader
        # (reader task absent/dead while clients depend on it) fails the probe
        # and k8s can route away from / restart this worker. Stays ok through a
        # normal transient reconnect (see ReconnectingBroadcaster.is_reader_healthy).
        broadcaster = server.pubsub.broadcaster
        if opal_server_config.BROADCAST_HEALTHCHECK_ENABLED and isinstance(
            broadcaster, ReconnectingBroadcaster
        ):
            healthy = broadcaster.is_reader_healthy()
            # Publish what the probe already decided. A wedged reader is
            # otherwise invisible outside this handler: where no liveness
            # probe runs, nothing acts on the 503 below.
            metrics.gauge(
                "opal_server.broadcaster_reader_healthy",
                1 if healthy else 0,
                tags={"pid": str(os.getpid())},
            )
            if not healthy:
                return JSONResponse(
                    status_code=503,
                    content={"status": "error", "broadcaster": "unhealthy"},
                )
            # Fleet purges reach this worker only through its own
            # subscription; it is entered as the worker starts.
            if (
                server.health.expects_backbone_subscription
                and server.health.backbone_subscribed is not True
            ):
                return JSONResponse(
                    status_code=503,
                    content={"status": "error", "pubsub": "no backbone subscription"},
                )
        if not _pubsub_route_mounted(app):
            return JSONResponse(
                status_code=503, content={"status": "error", "pubsub": "not mounted"}
            )
        if opal_server_config.SCOPES and opal_server_config.SCOPES_READY_REQUIRED_REPOS:
            missing = required_clones.missing(Path(opal_server_config.BASE_DIR))
            metrics.gauge(
                "opal_server.scopes.ready_clones_missing",
                len(missing),
                tags={"pid": str(os.getpid())},
            )
            if missing:
                # Source ids, never a URL: a URL can carry a credential.
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "scopes": "clones missing",
                        "missing": missing,
                    },
                )
        return {"status": "ok"}
