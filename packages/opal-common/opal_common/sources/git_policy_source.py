from typing import Optional

from git import Repo
from opal_common.git.branch_tracker import BranchTracker
from opal_common.git.exceptions import GitFailed
from opal_common.git.repo_cloner import RepoCloner
from opal_common.logger import logger
from opal_common.sources.base_policy_source import BasePolicySource


class GitPolicySource(BasePolicySource):
    """Watches a git repository for changes and can trigger callbacks when
    detecting new commits on the tracked branch.

    Checking for changes is done following a git pull from a tracked
    remote. The pull can be either triggered by a method (i.e: you can
    call it from a webhook) or can be triggered periodically by a polling
    task.

    Args:
        remote_source_url(str): the base address to request the policy from
        local_clone_path(str):  path for the local git to manage policies
        branch_name(str):  name of remote branch in git to pull, default to master
        ssh_key (str, optional): private ssh key used to gain access to the cloned repo
        polling_interval(int):  how many seconds need to wait between polling
        request_timeout(int):  how many seconds need to wait until timout
    """

    def __init__(
        self,
        remote_source_url: str,
        local_clone_path: str,
        branch_name: str = "master",
        ssh_key: Optional[str] = None,
        polling_interval: int = 0,
        request_timeout: int = 0,
    ):
        super().__init__(
            remote_source_url=remote_source_url,
            local_clone_path=local_clone_path,
            polling_interval=polling_interval,
        )

        self._cloner = RepoCloner(
            remote_source_url,
            local_clone_path,
            branch_name=branch_name,
            ssh_key=ssh_key,
            clone_timeout=request_timeout,
        )
        self._branch_name = branch_name
        self._tracker = None

    async def get_initial_policy_state_from_remote(self):
        """init remote data to local repo."""
        try:
            try:
                # Check if path already contains valid repo
                repo = Repo(self._cloner.path)
            except:
                # If it doesn't - clone it
                result = await self._cloner.clone()
                repo = result.repo
            else:
                # If it does - validate remote url is correct and checkout required branch
                remote_urls = list(repo.remote().urls)
                if not self._cloner.url in remote_urls:
                    # Don't bother with remove and reclone because this case shouldn't happen on reasobable usage
                    raise GitFailed(
                        RuntimeError(
                            f"Existing repo has wrong remote url: {remote_urls}"
                        )
                    )
                else:
                    logger.info(
                        "SKIPPED cloning policy repo, found existing repo at '{path}' with remotes: {remote_urls})",
                        path=self._cloner.path,
                        remote_urls=remote_urls,
                    )
        except GitFailed as e:
            await self._on_git_failed(e)
            return

        self._tracker = BranchTracker(
            repo=repo,
            branch_name=self._branch_name,
        )

    async def check_for_changes(self):
        """Calling this method will trigger a git pull from the tracked remote.

        If after the pull the watcher detects new commits, it will call
        the callbacks registered with _on_new_policy().
        """
        logger.info(
            "Pulling changes from remote: '{remote}'",
            remote=self._tracker.tracked_remote.name,
        )
        has_changes, prev, latest = self._tracker.pull()
        if not has_changes:
            logger.info("No new commits: HEAD is at '{head}'", head=latest.hexsha)
        else:
            logger.info(
                "Found new commits: old HEAD was '{prev_head}', new HEAD is '{new_head}'",
                prev_head=prev.hexsha,
                new_head=latest.hexsha,
            )
            await self._on_new_policy(old=prev, new=latest)
