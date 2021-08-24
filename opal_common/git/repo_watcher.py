import asyncio
from typing import Callable, Coroutine, List, Optional
from git.objects import Commit

from opal_common.git.branch_tracker import BranchTracker
from opal_common.git.repo_cloner import RepoCloner
from opal_common.git.exceptions import GitFailed
from opal_common.logger import logger


OnNewCommitsCallback = Callable[[Commit, Commit], Coroutine]
OnGitFailureCallback = Callable[[Exception], Coroutine]


class RepoWatcher:
    """
    Watches a git repository for changes and can trigger callbacks
    when detecting new commits on the tracked branch.

    Checking for changes is done following a git pull from a tracked
    remote. The pull can be either triggered by a method (i.e: you can
    call it from a webhook) or can be triggered periodically by a polling
    task.
    """
    def __init__(
        self,
        repo_url: str,
        clone_path: str,
        branch_name: str = "master",
        remote_name: str = "origin",
        ssh_key: Optional[str] = None,
        polling_interval: int = 0,
        clone_timeout: int = 0,
    ):
        self._cloner = RepoCloner(repo_url, clone_path, branch_name=branch_name, ssh_key=ssh_key, clone_timeout=clone_timeout)
        self._branch_name = branch_name
        self._remote_name = remote_name
        self._tracker = None
        self._on_failure_callbacks: List[OnNewCommitsCallback] = []
        self._on_new_commits_callbacks: List[OnGitFailureCallback] = []
        self._polling_interval = polling_interval
        self._polling_task = None

    def on_new_commits(self, callback: OnNewCommitsCallback):
        """
        Register a callback that will be called when new commits
        are detected on the monitored repo (after a pull).
        """
        self._on_new_commits_callbacks.append(callback)

    def on_git_failed(self, callback: OnGitFailureCallback):
        """
        Register a callback that will be called when one of the underlying
        git actions fails without possibility for recovery, i.e: we try to
        clone from a bad repo_url, etc.
        """
        self._on_failure_callbacks.append(callback)

    async def run(self):
        """
        clones the repo and potentially starts the polling task
        """
        try:
            result = await self._cloner.clone()
        except GitFailed as e:
            await self._on_git_failed(e)
            return

        self._tracker = BranchTracker(
            repo=result.repo,
            branch_name=self._branch_name,
            remote_name=self._remote_name
        )
        # if the repo exists locally, we need to git pull when the watcher starts
        if not result.cloned_from_remote:
            self._tracker.pull()

        if (self._polling_interval > 0):
            logger.info("Launching polling task, interval: {interval} seconds", interval=self._polling_interval)
            self._start_polling_task()
        else:
            logger.info("Polling task is off")

    async def stop(self):
        return await self._stop_polling_task()

    async def check_for_changes(self):
        """
        calling this method will trigger a git pull from the tracked remote.
        if after the pull the watcher detects new commits, it will call the
        callbacks registered with on_new_commits().
        """
        logger.info("Pulling changes from remote: '{remote}'", remote=self._tracker.tracked_remote.name)
        has_changes, prev, latest = self._tracker.pull()
        if not has_changes:
            logger.info("No new commits: HEAD is at '{head}'", head=latest.hexsha)
        else:
            logger.info("Found new commits: old HEAD was '{prev_head}', new HEAD is '{new_head}'", prev_head=prev.hexsha, new_head=latest.hexsha)
            await self._on_new_commits(old=prev, new=latest)

    async def _do_polling(self):
        """
        optional task to periodically check the remote for changes (git pull and compare hash).
        """
        while True:
            await asyncio.sleep(self._polling_interval)
            await self.check_for_changes()

    def _start_polling_task(self):
        if self._polling_task is None and self._polling_interval > 0:
            self._polling_task = asyncio.create_task(self._do_polling())

    async def _stop_polling_task(self):
        if self._polling_task is not None:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

    async def _on_new_commits(self, old: Commit, new: Commit):
        """
        triggers callbacks registered with on_new_commits().
        """
        await self._run_callbacks(self._on_new_commits_callbacks, old, new)

    async def _on_git_failed(self, exc: Exception):
        """
        will be triggered if a git failure occurred (i.e: repo does not exist, can't clone, etc).
        triggers callbacks registered with on_git_failed().
        """
        await self._run_callbacks(self._on_failure_callbacks, exc)

    async def _run_callbacks(self, handlers, *args, **kwargs):
        """
        triggers a list of callbacks
        """
        await asyncio.gather(*(callback(*args, **kwargs) for callback in handlers))
