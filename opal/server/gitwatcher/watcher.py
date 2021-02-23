import re
import asyncio

from typing import Callable, Optional, Tuple, List
from pathlib import Path
from tenacity import retry, wait_fixed, stop_after_attempt
from git import Repo, GitError, GitCommandError

from opal.common.logger import get_logger
from opal.common.utils import AsyncioEventLoopThread
from opal.common.git.repo_tracker import RepoTracker, GitFailed
from opal.common.git.repo_utils import GitActions, DirActions
from opal.common.config import POLICY_REPO_MAIN_BRANCH, POLICY_REPO_MAIN_REMOTE
from opal.server.config import (
    POLICY_REPO_URL,
    POLICY_REPO_CLONE_PATH,
    POLICY_REPO_POLLING_INTERVAL,
    OPA_FILE_EXTENSIONS
)
from opal.server.gitwatcher.publisher import policy_publisher

logger = get_logger("Policy Watcher")

# retry in case of temp network error
REPO_CLONE_RETRY_CONFIG = dict(wait=wait_fixed(5), stop=stop_after_attempt(2))

def policy_topics(paths: List[Path]):
    return ["policy:{}".format(str(path)) for path in paths]

class PolicyWatcher:
    def __init__(
        self,
        repo_url: str = POLICY_REPO_URL,
        clone_path: str = POLICY_REPO_CLONE_PATH,
        branch_name: str = POLICY_REPO_MAIN_BRANCH,
        remote_name: str = POLICY_REPO_MAIN_REMOTE,
        file_extensions: Tuple[str] = OPA_FILE_EXTENSIONS,
        polling_interval: int = POLICY_REPO_POLLING_INTERVAL,
        on_failure: Optional[Callable] = None,
    ):
        self._thread = AsyncioEventLoopThread(name="PolicyWatcherThread")
        if repo_url is None:
            raise ValueError("must provide repo url!")

        self._repo_url = repo_url
        self._clone_path = clone_path
        self._branch_name = branch_name
        self._remote_name = remote_name
        self._file_extensions = file_extensions
        self._polling_interval = polling_interval
        self._on_failure = on_failure

        self._tracker = None

    def start(self):
        logger.info("Launching repo watcher")
        self._thread.create_task(self._run_watcher())
        self._thread.start()

    def stop(self):
        logger.info("Stopping repo watcher")
        self._thread.stop()

    def trigger_pull(self):
        """
        this method can be called inside the thread (by the polling task)
        or outside the thread (by the webhook route) and will cause the
        watcher to pull changes from the remote and (if they exist) publish
        policy changes to clients.
        """
        self._thread.run_coro(self._pull_and_publish_updates())

    def _fail(self):
        self.stop()
        if self._on_failure is not None:
            self._on_failure()

    async def _run_watcher(self):
        try:
            logger.info("Cloning policy repo", url=self._repo_url)
            repo, fresh_clone = await self._clone()
        except GitFailed:
            self._fail()

        self._tracker = RepoTracker(
            repo=repo,
            branch_name=self._branch_name,
            remote_name=self._remote_name
        )
        # if the repo exists locally, we need to git pull when the watcher starts
        if not fresh_clone:
            logger.info("Pulling changes from remote", remote=self._tracker.tracked_remote.name)
            self._tracker.pull()

        self._publish_full_manifest()

        # potentially start polling task
        if (self._polling_interval > 0):
            logger.info("Launching polling task", interval=self._polling_interval)
            asyncio.create_task(self._polling_task())
        else:
            logger.info("Polling task is off")

    async def _polling_task(self):
        while True:
            await asyncio.sleep(self._polling_interval)
            self.trigger_pull()

    async def _clone(self) -> Tuple[Repo, bool]:
        git_path = Path(self._clone_path) / Path(".git")
        if git_path.exists():
            logger.info("Repo already exists", repo_path=self._clone_path)
            return Repo(self._clone_path), False

        # else, need to clone the repo
        try:
            repo = await self._clone_or_retry()
        except (GitError, GitCommandError) as e:
            logger.critical("cannot clone policy repo", error=e)
            raise GitFailed(e)
        else:
            logger.info("Clone succeeded", repo_path=self._clone_path)
            return repo, True

    @retry(**REPO_CLONE_RETRY_CONFIG)
    async def _clone_or_retry(self) -> Repo:
        return Repo.clone_from(url=self._repo_url, to_path=self._clone_path)

    async def _pull_and_publish_updates(self):
        """
        called either by polling task or by webhook and git pull from origin
        """
        logger.info("Pulling changes from remote", remote=self._tracker.tracked_remote.name)
        has_changes, prev, latest = self._tracker.pull()
        if not has_changes:
            logger.info("No new commits", new_head=latest.hexsha)
        else:
            logger.info("Found new commits", prev_head=prev.hexsha, new_head=latest.hexsha)
            # TODO: publish diff
            self._publish_full_manifest()

    def _publish_full_manifest(self):
        """
        publishes policy topics matching all relevant directories in tracked repo,
        prompting the client to ask for *all* contents of these directories (and not just diffs).
        """
        commit = self._tracker.latest_commit
        all_paths = GitActions.all_files_in_repo(
            commit, self._file_extensions)
        directories = DirActions.parents(all_paths)
        logger.info("Publishing policy update", directories=[str(d) for d in directories])
        topics = policy_topics(directories)
        policy_publisher.publish_updates(topics=topics, data=commit.hexsha)

policy_watcher = PolicyWatcher()