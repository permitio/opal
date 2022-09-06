import asyncio
import os
from functools import partial
from typing import Callable, Coroutine, List, Union

from git.objects.commit import Commit
from opal_common.logger import logger

OnNewPolicyCallback = Callable[[Commit, Commit], Coroutine]
OnPolicyFailureCallback = Callable[[Exception], Coroutine]


class BasePolicySource:
    """Base class to support git and api policy source.

    Args:
        remote_source_url(str): the base address to request the policy from
        local_clone_path(str):  path for the local git to manage policies
        polling_interval(int):  how many seconds need to wait between polling
    """

    def __init__(
        self,
        remote_source_url: str,
        local_clone_path: str,
        polling_interval: int = 0,
    ):
        self._on_failure_callbacks: List[OnNewPolicyCallback] = []
        self._on_new_policy_callbacks: List[OnPolicyFailureCallback] = []
        self._polling_interval = polling_interval
        self._polling_task = None
        self.remote_source_url = remote_source_url
        self.local_clone_path = os.path.expanduser(local_clone_path)

    def add_on_new_policy_callback(self, callback: OnNewPolicyCallback):
        """Register a callback that will be called when new policy are detected
        on the monitored repo (after a pull)."""
        self._on_new_policy_callbacks.append(callback)

    def add_on_failure_callback(self, callback: OnPolicyFailureCallback):
        """Register a callback that will be called when failure occurred."""
        self._on_failure_callbacks.append(callback)

    async def get_initial_policy_state_from_remote(self):
        """init remote data to local repo."""
        raise NotImplementedError()

    async def check_for_changes(self):
        """trigger check for policy change."""
        raise NotImplementedError()

    async def run(self):
        """potentially starts the polling task."""
        await self.get_initial_policy_state_from_remote()

        if self._polling_interval > 0:
            logger.info(
                "Launching polling task, interval: {interval} seconds",
                interval=self._polling_interval,
            )
            self._start_polling_task(self.check_for_changes)
        else:
            logger.info("Polling task is off")

    async def stop(self):
        return await self._stop_polling_task()

    def _start_polling_task(self, polling_task):
        if self._polling_task is None and self._polling_interval > 0:
            self._polling_task = asyncio.create_task(self._do_polling(polling_task))

    async def _do_polling(self, polling_task):
        """optional task to periodically check the remote for changes (git pull
        and compare hash)."""
        while True:
            try:
                await polling_task()
            except Exception as ex:
                logger.error(
                    "Error occured during polling task {task}: {err}",
                    task=polling_task.__name__,
                    err=ex,
                )
            await asyncio.sleep(self._polling_interval)

    async def _stop_polling_task(self):
        if self._polling_task is not None:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

    async def _on_new_policy(self, old: Commit, new: Commit):
        """triggers callbacks registered with on_new_policy()."""
        await self._run_callbacks(self._on_new_policy_callbacks, old, new)

    async def _on_failed(self, exc: Exception):
        """will be triggered if a failure occurred.

        triggers callbacks registered with on_git_failed().
        """
        await self._run_callbacks(self._on_failure_callbacks, exc)

    async def _run_callbacks(self, handlers, *args, **kwargs):
        """triggers a list of callbacks."""
        await asyncio.gather(*(callback(*args, **kwargs) for callback in handlers))

    async def _on_git_failed(self, exc: Exception):
        """will be triggered if a git failure occurred (i.e: repo does not
        exist, can't clone, etc).

        triggers callbacks registered with on_git_failed().
        """
        await self._run_callbacks(self._on_failure_callbacks, exc)
