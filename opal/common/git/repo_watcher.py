import asyncio
from typing import Callable, Coroutine, List
from git.objects import Commit

from opal.common.git.branch_tracker import BranchTracker
from opal.common.git.repo_cloner import RepoCloner
from opal.common.git.repo_utils import GitFailed
from opal.common.logger import get_logger
from opal.common.utils import AsyncioEventLoopThread

logger = get_logger("opal.git.watcher")


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
        polling_interval: int = 0,
    ):
        self._thread = AsyncioEventLoopThread(name="PolicyWatcherThread")
        self._cloner = RepoCloner(repo_url, clone_path)
        self._branch_name = branch_name
        self._remote_name = remote_name
        self._tracker = None
        self._polling_interval = polling_interval
        self._on_failure_callbacks: List[OnNewCommitsCallback] = []
        self._on_new_commits_callbacks: List[OnGitFailureCallback] = []

    def start(self):
        logger.info("Launching repo watcher")
        self._thread.create_task(self._init_repo())
        self._thread.start()

    def stop(self):
        logger.info("Stopping repo watcher")
        self._thread.stop()

    def trigger(self):
        """
        this method can be called inside the thread (by the polling task)
        or outside the thread (by the webhook route) and will cause the
        watcher to pull changes from the remote and (if they exist) publish
        policy changes to clients.
        """
        self._thread.create_task(self._check_for_changes())

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

    async def _init_repo(self):
        """
        initial task: clones the repo and potentially starts the polling task
        """
        try:
            result = self._cloner.clone()
        except GitFailed as e:
            await self._fail(e)

        self._tracker = BranchTracker(
            repo=result.repo,
            branch_name=self._branch_name,
            remote_name=self._remote_name
        )
        # if the repo exists locally, we need to git pull when the watcher starts
        if not result.cloned_from_remote:
            self._tracker.pull()

        if (self._polling_interval > 0):
            logger.info("Launching polling task", interval=self._polling_interval)
            asyncio.create_task(self._polling_task())
        else:
            logger.info("Polling task is off")

    async def _polling_task(self):
        """
        optional task to periodically check the remote for changes (git pull and compare hash).
        """
        while True:
            await asyncio.sleep(self._polling_interval)
            self.trigger()

    async def _check_for_changes(self):
        """
        called either by polling task or by webhook and git pull from origin
        """
        logger.info("Pulling changes from remote", remote=self._tracker.tracked_remote.name)
        has_changes, prev, latest = self._tracker.pull()
        if not has_changes:
            logger.info("No new commits", new_head=latest.hexsha)
        else:
            logger.info("Found new commits", prev_head=prev.hexsha, new_head=latest.hexsha)
            await self._on_new_commits(old=prev, new=latest)

    async def _fail(self, exc: Exception):
        await self._on_git_failed(exc)
        self.stop()

    async def _on_new_commits(self, old: Commit, new: Commit):
        await self._run_callbacks(self._on_new_commits_callbacks, old, new)

    async def _on_git_failed(self, exc: Exception):
        await self._run_callbacks(self._on_failure_callbacks, exc)

    async def _run_callbacks(self, handlers, *args, **kwargs):
        await asyncio.gather(*(callback(*args, **kwargs) for callback in handlers))
