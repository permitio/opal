import asyncio
from typing import Callable, Coroutine, List, Optional
from git.objects import Commit

from opal_common.git.branch_tracker import BranchTracker
from opal_common.git.repo_cloner import RepoCloner
from opal_common.git.exceptions import GitFailed
from opal_common.logger import logger
from opal_common.sources.base_policy_source import BasePolicySource


OnNewCommitsCallback = Callable[[Commit, Commit], Coroutine]
OnGitFailureCallback = Callable[[Exception], Coroutine]


class GitPolicySource(BasePolicySource):
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
        remote_source_url: str,
        local_clone_path: str,
        branch_name: str = "master",
        remote_name: str = "origin",
        ssh_key: Optional[str] = None,
        polling_interval: int = 0,
        request_timeout: int = 0,
    ):
        super().__init__(remote_source_url=remote_source_url, local_clone_path=local_clone_path,
                         polling_interval=polling_interval, request_timeout=request_timeout)

        self._cloner = RepoCloner(remote_source_url, local_clone_path, branch_name=branch_name, ssh_key=ssh_key, clone_timeout=request_timeout)
        self._branch_name = branch_name
        self._remote_name = remote_name
        self._tracker = None

    async def config(self):
        """
        init remote data to local repo
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

    async def run(self):
        """
        potentially starts the polling task
        """
        await self.config()
        if (self._polling_interval > 0):
            logger.info("Launching polling task, interval: {interval} seconds", interval=self._polling_interval)
            self._start_polling_task(self.check_for_changes)
        else:
            logger.info("Polling task is off")

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
            logger.info("Found new commits: old HEAD was '{prev_head}', new HEAD is '{new_head}'",
                        prev_head=prev.hexsha, new_head=latest.hexsha)
            await self._on_new_policy(old=prev, new=latest)
