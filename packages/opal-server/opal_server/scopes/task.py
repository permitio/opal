import asyncio
import datetime
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from fastapi_websocket_pubsub import Topic
from opal_common.logger import configure_logs, logger, logs_configured
from opal_server import health
from opal_server.config import opal_server_config
from opal_server.git_cli import (
    close_leftover_lock_fds,
    validate_git_cli_settings,
    wait_for_background_ops,
)
from opal_server.git_fetcher import (
    GitPolicyFetcher,
    drain_git_ops,
    git_busy_count,
    reclone_hung_enabled,
    reclone_hung_scope_clones,
    shutdown_git_executor,
    sweep_scope_clone_leftovers,
)
from opal_server.metrics_setup import configure_server_metrics
from opal_server.policy.watcher.task import BasePolicyWatcherTask
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from opal_server.redis_utils import RedisDB
from opal_server.scopes.missing_scope import validate_missing_scope_settings
from opal_server.scopes.orphans import OrphanCloneSweeper, orphan_sweep_interval
from opal_server.scopes.purge import LeaderScopePurger
from opal_server.scopes.readiness import required_clones, validate_required_repos
from opal_server.scopes.scope_repository import ScopeRepository
from opal_server.scopes.service import ScopesService


class _UnknownChildWarningFilter(logging.Filter):
    """Drops asyncio's warning about a child reaped before it got to it."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "will report returncode 255" not in record.getMessage()


# Upper bound on the shutdown drain of in-flight scope purges. The drain is
# best-effort: a purge's rmtree runs on a worker thread and completes whether or
# not we are still awaiting it. No later purge will name a deleted scope's
# source, so what is abandoned before it starts stays until the orphan sweep
# (SCOPES_ORPHAN_SWEEP_INTERVAL, off by default) reclaims it. Blocking shutdown
# longer would be strictly worse —
# stop() runs while the leadership lock is still held, so no other worker can
# take over, and k8s's terminationGracePeriodSeconds (30s by default) would
# SIGKILL us anyway.
_PURGE_DRAIN_TIMEOUT = 5.0


@dataclass
class _QueuedPass:
    """The pass that starts once the running one ends, and its requests."""

    only_poll_updates: bool
    honor_backoff: bool
    done: asyncio.Future
    requests: int = 0


class _SyncPassQueue:
    """Runs the leader's scope sync passes one at a time.

    At most one pass runs and one is queued. A request made while a pass
    is queued joins it, so every request is served by a pass that
    started after it was made, and a burst of requests during a pass
    costs one more pass. The queued pass polls only when every request
    it serves asked for poll-only, and honours the source backoff only
    when every one does: a refresh of every scope that joins a periodic
    request still gets a full pass without the backoff. A pass ends with
    its repacks, so the next one starts only once they are done.
    """

    def __init__(self, run_pass: Callable[[bool, bool], Awaitable[None]]) -> None:
        self._run_pass = run_pass
        self._queued: Optional[_QueuedPass] = None
        self._drain_task: Optional[asyncio.Task] = None
        self._stopped = False

    async def request(self, *, only_poll_updates: bool, honor_backoff: bool) -> None:
        """Wait for a sync pass that starts after this call.

        Returns once that pass ended, whether it succeeded or failed (a
        failure is logged where the pass runs). Returns at once after stop().
        Cancelling the caller leaves the pass to the other requests it
        serves.

        Raises:
            asyncio.CancelledError: stop() cancelled the pass this waits for.
        """
        done = self.enqueue(
            only_poll_updates=only_poll_updates, honor_backoff=honor_backoff
        )
        if done is not None:
            await asyncio.shield(done)

    def enqueue(
        self, *, only_poll_updates: bool, honor_backoff: bool
    ) -> Optional[asyncio.Future]:
        """Ask for a sync pass as request() does, without waiting for it.

        Returns:
            The future the pass resolves once it ended, or None after stop().
        """
        if self._stopped:
            return None
        queued = self._queued
        if queued is None:
            queued = _QueuedPass(
                only_poll_updates=only_poll_updates,
                honor_backoff=honor_backoff,
                done=asyncio.get_running_loop().create_future(),
            )
            self._queued = queued
        else:
            queued.only_poll_updates = queued.only_poll_updates and only_poll_updates
            queued.honor_backoff = queued.honor_backoff and honor_backoff
        queued.requests += 1
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain())
        return queued.done

    async def stop(self) -> None:
        """Cancel the running pass and the queued one; idempotent.

        Their waiters get CancelledError, and later requests return at
        once.
        """
        self._stopped = True
        task, self._drain_task = self._drain_task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._cancel_queued()

    def _cancel_queued(self) -> None:
        queued, self._queued = self._queued, None
        if queued is not None:
            queued.done.cancel()

    async def _drain(self) -> None:
        # No await between the loop's last check and the return: a request
        # made meanwhile would find this task still running and wait forever.
        while self._queued is not None:
            current, self._queued = self._queued, None
            started = time.monotonic()
            try:
                await self._run_pass(current.only_poll_updates, current.honor_backoff)
            except asyncio.CancelledError:
                current.done.cancel()
                self._cancel_queued()
                raise
            except Exception:
                logger.exception("Scope sync pass failed")
            finally:
                if not current.done.done():
                    current.done.set_result(None)
            logger.info(
                "Scope sync pass for {requests} request(s) ended after {seconds:.1f}s",
                requests=current.requests,
                seconds=time.monotonic() - started,
            )


class ScopesPolicyWatcherTask(BasePolicyWatcherTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set in start(); None means "nothing to unsubscribe" (stop() without a
        # successful start, or a second stop()).
        self._purger_sub_id = None

        self._scopes = ScopeRepository(RedisDB(opal_server_config.REDIS_URL))
        self._service = ScopesService(
            base_dir=Path(opal_server_config.BASE_DIR),
            scopes=self._scopes,
            pubsub_endpoint=self._pubsub_endpoint,
        )
        self._purger = LeaderScopePurger(
            base_dir=Path(opal_server_config.BASE_DIR),
            scopes=self._scopes,
            pubsub_endpoint=self._pubsub_endpoint,
        )
        self._passes = _SyncPassQueue(self._run_pass)
        # Set in start() when the broadcaster reports backbone gaps.
        self._remove_gap_listener: Optional[Callable[[], None]] = None

    async def start(self):
        await super().start()
        # Leader-only purge authorization: this task starts only on the leader, so
        # registering here (not at worker boot) preserves the invariant that
        # the leader is the only mutator on sync paths (see the note in
        # scopes/purge.py — a delete also removes on the serving worker).
        #
        # Registered under a DEDICATED subscriber id rather than through
        # PubSubEndpoint.subscribe, which files every server-side subscription
        # under one shared endpoint id: EventNotifier.unsubscribe deletes that
        # id's WHOLE callback list for the topic, so unsubscribing by topic in
        # stop() would also drop the every-worker handle_purge_message
        # subscription (registered once at boot in server.py, never re-added) —
        # leaving this process deaf to fleet purges for the rest of its life.
        # Our own id makes the leader subscription independently removable.
        self._purger_sub_id = self._pubsub_endpoint.notifier.gen_subscriber_id()
        await self._pubsub_endpoint.notifier.subscribe(
            self._purger_sub_id,
            [opal_server_config.SCOPES_PURGE_CHANNEL],
            self._purger.handle,
        )
        # With POLICY_REFRESH_INTERVAL <= 0 this boot sync is the ONLY
        # pass-originated sync this process ever runs, so a source that failed
        # transiently during the pre-fork preload (whose entry survives
        # reset_caches on purpose) must not be inherited — it would never be
        # attempted again. Clearing the inherited entries (rather than not
        # honouring the backoff) keeps the within-pass property: phase-2
        # duplicates of a source that fails in THIS pass are still collapsed
        # to one attempt.
        # Clearing the whole dict is safe here: this runs once, right after
        # this process won leadership, and a freshly forked worker cannot have
        # recorded anything of its own before that (only leaders sync).
        if opal_server_config.POLICY_REFRESH_INTERVAL <= 0:
            GitPolicyFetcher.source_backoff.clear()
        self._remove_gap_listener = self._listen_for_backbone_gaps()
        # Honours the backoff: this process may have been forked from a
        # master whose preload already found which repos are unreachable,
        # and attempting all of them again at boot is the storm the backoff
        # exists to prevent.
        self._tasks.append(
            asyncio.create_task(
                self._passes.request(only_poll_updates=False, honor_backoff=True)
            )
        )

        if opal_server_config.POLICY_REFRESH_INTERVAL > 0:
            self._tasks.append(asyncio.create_task(self._periodic_polling()))

        interval = orphan_sweep_interval()
        if interval > 0:
            sweeper = OrphanCloneSweeper(
                Path(opal_server_config.BASE_DIR), self._scopes, interval
            )
            self._tasks.append(asyncio.create_task(sweeper.run()))

    async def stop(self):
        # stop() runs TWICE on the normal path — once from
        # BasePolicyWatcherTask.__aexit__ (server.py's `async with self.watcher`)
        # and again from stop_server_background_tasks — so every step here is
        # idempotent: the subscriber id is consumed on first use, signal_stop and
        # the drain are no-ops once done.
        #
        # Stop accepting new purge messages first (cheap, non-blocking).
        if self._purger_sub_id is not None:
            sub_id, self._purger_sub_id = self._purger_sub_id, None
            try:
                await self._pubsub_endpoint.notifier.unsubscribe(
                    sub_id, [opal_server_config.SCOPES_PURGE_CHANNEL]
                )
            except Exception:
                logger.exception("Failed to unsubscribe scope purge handler on stop")
        self._purger.signal_stop()
        if self._remove_gap_listener is not None:
            remove, self._remove_gap_listener = self._remove_gap_listener, None
            remove()

        # Cancel the passes and our tasks BEFORE draining the purges, not
        # after: a queued purge first waits on GitPolicyFetcher.lock_source,
        # which a sync holds across a clone/fetch (up to
        # SCOPES_GIT_FETCH_TIMEOUT, and unbounded when that is 0). Draining
        # first would wait on a lock whose release requires the very
        # cancellation the drain is blocking — an unrecoverable shutdown hang,
        # taken while the leadership lock is still held. The passes first:
        # they run in the queue's own task, which super().stop() does not
        # cancel, only the requests waiting for them.
        await self._passes.stop()
        result = await super().stop()

        # Best-effort, bounded (see _PURGE_DRAIN_TIMEOUT).
        #
        # ONLY the purger is drained here. The DELETE floor's tasks live on the
        # ScopesService that init_scope_router received (built in server.py), NOT
        # on self._service — the watcher constructs its own, and only ever syncs
        # with it. Draining self._service gathered an empty set. This is also the
        # wrong place structurally: the watcher exists only on the leader, while
        # a DELETE usually lands on a non-leader. That drain is per-worker, on
        # OpalServer.stop_server_background_tasks.
        try:
            await asyncio.wait_for(self._purger.stop(), timeout=_PURGE_DRAIN_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(
                "Abandoned in-flight scope purges at shutdown after {timeout}s; "
                "their clone dirs stay on disk until the source is purged again",
                timeout=_PURGE_DRAIN_TIMEOUT,
            )
        return result

    def _listen_for_backbone_gaps(self) -> Optional[Callable[[], None]]:
        """Run a sync pass after each broadcaster backbone gap; returns the
        function that stops it, or None when there is nothing to listen to.

        A refresh published while this leader's backbone subscription
        was down never reaches it, and a gap resync only reconnects
        clients, which then fetch from clones nothing advanced. Only
        with the reconnecting broadcaster, which reports gaps, and with
        BROADCAST_RESYNC_ON_RECONNECT on.
        """
        broadcaster = self._pubsub_endpoint.broadcaster
        if not opal_server_config.BROADCAST_RESYNC_ON_RECONNECT or not isinstance(
            broadcaster, ReconnectingBroadcaster
        ):
            return None
        return broadcaster.add_reconnect_listener(self._resync_after_gap)

    async def _resync_after_gap(self) -> None:
        # The pass is not waited for: the broadcaster's recovery waits for
        # its listeners, and must not wait for a whole pass. Gaps during a
        # pass join the one pass queued after it.
        logger.info("Broadcaster backbone gap ended; requesting a scope sync pass")
        self._passes.enqueue(only_poll_updates=False, honor_backoff=True)

    async def _run_pass(self, only_poll_updates: bool, honor_backoff: bool):
        # Only through self._passes, which logs what this raises.
        try:
            await self._service.sync_scopes(
                only_poll_updates=only_poll_updates, honor_backoff=honor_backoff
            )
        except Exception:
            health.leader_heartbeat.note_attempt(False)
            raise
        health.leader_heartbeat.note_attempt(True)

    async def _periodic_polling(self):
        try:
            while True:
                await asyncio.sleep(opal_server_config.POLICY_REFRESH_INTERVAL)
                logger.info("Periodic sync")
                await self._passes.request(only_poll_updates=True, honor_backoff=True)

        except asyncio.CancelledError:
            logger.info("Periodic sync cancelled")
            raise

    async def trigger(self, topic: Topic, data: Any):
        if data is not None and isinstance(data, dict):
            # Refresh single scope
            try:
                source_id = await self._service.sync_scope(
                    scope_id=data["scope_id"],
                    force_fetch=data.get("force_fetch", False),
                    hinted_hash=data.get("hinted_hash"),
                    req_time=datetime.datetime.now(),
                    # PUT /scopes sets it when the scope's source changed.
                    notify_all=bool(data.get("repointed", False)),
                    # A sync a bundle request asked for (its branch was missing).
                    honor_backoff=bool(data.get("honor_backoff", False)),
                    # The sync a client with no policy asked for: its wait.
                    fresh_within=data.get("fresh_within"),
                )
            except KeyError:
                logger.warning(
                    "Got invalid keyword args for single scope refresh: %s", data
                )
                return
            except Exception:
                health.leader_heartbeat.note_attempt(False)
                raise
            health.leader_heartbeat.note_attempt(True)
            if source_id is not None:
                # Outside a pass nothing else repacks the clone this sync may
                # have left at SCOPES_GIT_REPACK_PACK_LIMIT, and with
                # POLICY_REFRESH_INTERVAL=0 (the default) no pass runs after
                # the boot one. The refresh's notification is out by now, and
                # every trigger is a task of its own, so the repack delays
                # only the next syncs of this clone. It waits for the clone's
                # lock, unlike a pass's, and leaves the clone to the pass
                # when one is running: see run_due_repack.
                await GitPolicyFetcher.run_due_repack(source_id, wait_for_lock=True)
        else:
            # Refresh all scopes. This branch is reached only from something
            # asking for a sync NOW — POST /scopes/refresh (the git-provider
            # webhook publishes on this topic too, but only when
            # POLICY_REPO_URL is set, which scopes mode does not use) — so it
            # does not honour the per-source backoff: the
            # sources an operator hits this endpoint for are precisely the ones
            # they have just repaired, and answering them with a silent skip
            # makes the endpoint useless in the only situation it is used.
            # Made while a pass runs, it waits for the next one.
            await self._passes.request(only_poll_updates=False, honor_backoff=False)

    @staticmethod
    def preload_scopes():
        """Clone all scopes repositories as part as server startup.

        This speeds up the first sync of scopes after workers are
        started. scripts/gunicorn_conf.py::when_ready configures logging
        before calling this; a caller that didn't (e.g. a custom
        GUNICORN_CONF) gets configure_logs() here, so the preload never
        logs through loguru's unscrubbed default handler.
        """
        if opal_server_config.SCOPES:
            if not logs_configured():
                configure_logs()
            # Before any clone, and before a worker exists to refuse to start.
            validate_git_cli_settings()
            validate_required_repos()
            validate_missing_scope_settings()
            # This runs in the gunicorn MASTER (scripts/gunicorn_conf.py::when_ready)
            # before any worker configured monitoring. Without
            # configure_server_metrics() the git metrics emitted during preload
            # (git_ops_in_flight, scopes.count, sources_in_backoff,
            # git_op_failures...) go out un-namespaced and never reach the
            # dashboards/monitors built on permit.opal.*.
            configure_server_metrics()
            logger.info("Preloading repo clones for scopes")

            redis_db = RedisDB(opal_server_config.REDIS_URL)
            scopes = ScopeRepository(redis_db)
            service = ScopesService(
                base_dir=Path(opal_server_config.BASE_DIR),
                scopes=scopes,
                pubsub_endpoint=None,
            )

            async def _preload():
                # Before the sync, while nothing else in this container uses
                # the clones: delete the ones whose git op was still hung when
                # its process ended, so the sync clones them fresh, as on a new
                # pod (see SCOPES_GIT_RECLONE_HUNG_ON_START). With the setting
                # off it only removes leftover hung-op markers, and needs no
                # scope list. In the same event loop as the sync, which reads
                # the scopes again: the Redis client binds its connections to
                # the loop that first uses them, so it cannot be reused across
                # asyncio.run calls.
                live_source_ids = (
                    {
                        GitPolicyFetcher.source_id(scope.policy)
                        for scope in await scopes.all()
                    }
                    if reclone_hung_enabled()
                    else None
                )
                reclone_hung_scope_clones(
                    Path(opal_server_config.BASE_DIR), live_source_ids
                )
                # No git runs yet in this container: what git ops of earlier
                # processes left in the clones (locks, partial packs, clones
                # half made, SSH key files) goes, whichever fetcher made them.
                # Never in the way of the start: whatever the sweep cannot do
                # is logged and left.
                try:
                    sweep_scope_clone_leftovers(Path(opal_server_config.BASE_DIR))
                except Exception as e:
                    logger.error(
                        "Preload: sweeping the scope clones failed: {err!r}", err=e
                    )
                # No repack here, where it would delay the start of every
                # worker: the preload's fetches only mark their clones due, the
                # marks are inherited across fork, and the leader's first pass
                # repacks.
                await service.sync_scopes(
                    notify_on_changes=False, run_due_repacks=False
                )
                # git command-line ops still being stopped finish on tasks of
                # this loop; the ones that do not by the end of the loop get
                # SIGKILL then, and their clones are cleaned up by the next op.
                if not await wait_for_background_ops(
                    opal_server_config.SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT
                ):
                    logger.warning(
                        "Preload: git command-line ops still being stopped "
                        "after {timeout}s; their process groups get SIGKILL now",
                        timeout=opal_server_config.SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT,
                    )

            async def _preload_and_close():
                # The client's pool keeps every connection it opened, one per
                # scope read in flight at once, and binds them to this loop: it
                # can close them only here, before asyncio.run closes the loop,
                # whatever the sync did. Left open, their sockets stay in the
                # master for as long as it lives, and reach every worker it
                # forks. A close that fails is logged and left: it is never in
                # the way of the start, nor in place of the preload's own error.
                try:
                    await _preload()
                finally:
                    try:
                        await redis_db.close()
                    except Exception as e:
                        logger.warning(
                            "Preload: closing its Redis client failed: {err!r}", err=e
                        )

            # The gunicorn master's SIGCHLD handler reaps every child, so
            # asyncio finds each git command-line op's process reaped already
            # and warns. git_cli reads git's exit status from the process's
            # output instead, so the warning means nothing here.
            unknown_child = _UnknownChildWarningFilter()
            asyncio_logger = logging.getLogger("asyncio")
            asyncio_logger.addFilter(unknown_child)
            try:
                asyncio.run(_preload_and_close())
            finally:
                asyncio_logger.removeFilter(unknown_child)
                # A clone's lock left open here would be held in every forked
                # worker for as long as it lives.
                close_leftover_lock_fds()

            # Bounded window for a just-finished clone/fetch to clear its in-flight
            # marker before teardown+fork. Ops still lingering (hung remote) are
            # left running; reset_caches's guard then skips freeing their handles.
            # A False return means the drain timed out with git ops STILL running:
            # those threads persist in the master across the fork, so a forked
            # worker can race them on the shared clone dir. Log it — this is the
            # one condition that carries that risk, and it must not be silent.
            # Only libgit2 ops can be left in flight here: a git command-line op
            # the end of the loop cut short got SIGKILL, and left flight.
            drained = drain_git_ops(opal_server_config.SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT)
            if not drained:
                logger.warning(
                    "Preload drain timed out ({timeout}s) with libgit2 git ops "
                    "still in flight ({in_flight}); their threads persist in the "
                    "master across fork. Consider raising "
                    "SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT or lowering "
                    "SCOPES_GIT_FETCH_TIMEOUT.",
                    timeout=opal_server_config.SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT,
                    in_flight=git_busy_count(),
                )

            # Clear git-op bookkeeping built during preload (in-flight markers
            # and the loop-bound live-op semaphore) so the gunicorn master does
            # not carry stale state into forked workers. Git ops run on per-op
            # daemon threads; there is no shared pool to tear down.
            shutdown_git_executor()

            # Drop every cached repo handle/lock/timestamp built during preload
            # so none of it is inherited by forked workers. Sync (the only path
            # that populates these caches) is leader-only, so a non-leader worker
            # that inherited a handle would only ever release it through the
            # fleet-wide purge broadcast. Since 0.9.9-rc.3 every worker keeps a
            # backbone reader when SCOPES is on and the broadcaster is the
            # reconnecting one, so that broadcast does reach client-less workers;
            # with BROADCAST_RECONNECT_ENABLED=false (legacy broadcaster) the reader
            # runs only while a client is connected and an inherited handle could
            # still be pinned for life — clearing here keeps both cases safe. The
            # on-disk clones remain; workers re-open handles lazily.
            GitPolicyFetcher.reset_caches()

            # Each worker forked from here starts with what this saw landed.
            missing = required_clones.missing(Path(opal_server_config.BASE_DIR))
            if missing:
                logger.warning(
                    "Preload finished without the required scope clones "
                    "{missing}: readiness waits for them",
                    missing=missing,
                )
            logger.warning("Finished preloading repo clones for scopes.")
