"""Background liveness probe lifecycle shared by policy-store clients.

`LivenessProbeMixin` periodically samples the policy engine's reachability
and folds the result into `is_healthy()` via the subclass-supplied
`_set_engine_reachable` hook. The mixin owns the probe task, the lock that
guards lifecycle transitions, and a single long-lived `aiohttp.ClientSession`
reused across samples.

Subclasses provide:
- `_probe_engine_reachable(session)` — issues one HTTP request and returns
  True iff the engine answered with a 2xx. Must not catch the exceptions
  the loop relies on (`aiohttp.ClientError`, `asyncio.TimeoutError`); the
  mixin's outer loop classifies and logs them.
- `_set_engine_reachable(value)` / `_get_engine_reachable()` — read/write
  the boolean storage location used by `is_healthy()`.
- `_probe_log_label` (optional) — a short human-readable label (e.g. "OPA",
  "Cedar") used in log messages.
"""
import asyncio
from abc import abstractmethod
from typing import Optional

import aiohttp
from opal_client.config import opal_client_config
from opal_client.logger import logger


class LivenessProbeMixin:
    _liveness_probe_task: Optional[asyncio.Task]
    _liveness_probe_lock: asyncio.Lock
    _liveness_probe_session: Optional[aiohttp.ClientSession]

    def _init_liveness_probe(self) -> None:
        """Initialize mixin state.

        Call from the subclass `__init__`.
        """
        self._liveness_probe_task = None
        self._liveness_probe_lock = asyncio.Lock()
        self._liveness_probe_session = None

    @property
    def _probe_log_label(self) -> str:
        return "policy store"

    @abstractmethod
    async def _probe_engine_reachable(self, session: aiohttp.ClientSession) -> bool:
        raise NotImplementedError

    @abstractmethod
    def _set_engine_reachable(self, value: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    def _get_engine_reachable(self) -> bool:
        raise NotImplementedError

    async def start_liveness_probe(self) -> None:
        """Spawn the background liveness probe task (idempotent).

        Holds `_liveness_probe_lock` around the check-then-act so two
        concurrent callers cannot both create a task. Runs the first probe
        synchronously so the initial reachability flag reflects the actual
        state of the engine, not the optimistic default.
        """
        if not opal_client_config.POLICY_STORE_LIVENESS_PROBE_ENABLED:
            logger.info(
                "{label} liveness probe disabled via POLICY_STORE_LIVENESS_PROBE_ENABLED",
                label=self._probe_log_label,
            )
            return

        async with self._liveness_probe_lock:
            existing = self._liveness_probe_task
            if existing is not None and not existing.done():
                return

            timeout_seconds = max(
                1,
                opal_client_config.POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS,
            )
            interval_seconds = max(
                1,
                opal_client_config.POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS,
            )

            session = aiohttp.ClientSession(
                trust_env=True,
                timeout=aiohttp.ClientTimeout(total=timeout_seconds),
            )

            initial_reachable = await self._sample_reachable(session)
            self._set_engine_reachable(initial_reachable)

            task = asyncio.create_task(
                self._liveness_probe_loop(session, interval_seconds)
            )
            task.add_done_callback(self._on_probe_task_done)

            self._liveness_probe_session = session
            self._liveness_probe_task = task

            logger.info(
                "Started {label} liveness probe (interval={interval}s, timeout={timeout}s, initial_reachable={reachable})",
                label=self._probe_log_label,
                interval=interval_seconds,
                timeout=timeout_seconds,
                reachable=initial_reachable,
            )

    async def stop_liveness_probe(self) -> None:
        """Cancel the probe task and close its session (idempotent)."""
        async with self._liveness_probe_lock:
            task = self._liveness_probe_task
            session = self._liveness_probe_session
            self._liveness_probe_task = None
            self._liveness_probe_session = None

        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "Error while stopping {label} liveness probe task",
                    label=self._probe_log_label,
                )

        if session is not None:
            await session.close()

    def _on_probe_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "{label} liveness probe task exited unexpectedly: {err}",
                label=self._probe_log_label,
                err=repr(exc),
            )

    async def _sample_reachable(self, session: aiohttp.ClientSession) -> bool:
        """Issue a single probe request, classifying expected failures.

        Network/timeout errors are folded into a False return at DEBUG.
        Any other exception propagates and is treated as an unexpected
        error by the loop.
        """
        try:
            return await self._probe_engine_reachable(session)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.debug(
                "{label} liveness probe failed: {err}",
                label=self._probe_log_label,
                err=repr(e),
            )
            return False

    async def _liveness_probe_loop(
        self, session: aiohttp.ClientSession, interval_seconds: int
    ) -> None:
        last_reachable: bool = self._get_engine_reachable()
        while True:
            try:
                reachable = await self._sample_reachable(session)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Survival net: an unexpected error here means a bug in the
                # probe path itself, not a real engine outage. Log clearly so
                # operators can distinguish the two.
                logger.warning(
                    "{label} liveness probe encountered an unexpected error "
                    "(treating engine as unreachable): {err}",
                    label=self._probe_log_label,
                    err=repr(e),
                )
                reachable = False

            self._set_engine_reachable(reachable)

            if reachable != last_reachable:
                if reachable:
                    logger.info(
                        "{label} liveness probe: engine became reachable",
                        label=self._probe_log_label,
                    )
                else:
                    logger.info(
                        "{label} liveness probe: engine became unreachable",
                        label=self._probe_log_label,
                    )
                last_reachable = reachable
            else:
                logger.debug(
                    "{label} liveness probe sample: reachable={reachable}",
                    label=self._probe_log_label,
                    reachable=reachable,
                )

            await asyncio.sleep(interval_seconds)
