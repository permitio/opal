from typing import Any, Optional, List
from functools import partial

from fastapi_websocket_pubsub import Topic
from opal_common.logger import logger
from opal_common.git.repo_watcher import RepoWatcher
from opal_common.topics.publisher import TopicPublisher
from opal_server.config import (
    POLICY_REPO_URL,
    POLICY_REPO_CLONE_PATH,
    POLICY_REPO_MAIN_BRANCH,
    POLICY_REPO_MAIN_REMOTE,
    POLICY_REPO_SSH_KEY,
    POLICY_REPO_POLLING_INTERVAL,
    OPA_FILE_EXTENSIONS,
)
from opal_server.policy.watcher.task import RepoWatcherTask
from opal_server.policy.watcher.callbacks import publish_changed_directories


def setup_watcher_task(
    publisher: TopicPublisher,
    repo_url: str = POLICY_REPO_URL,
    clone_path: str = POLICY_REPO_CLONE_PATH,
    branch_name: str = POLICY_REPO_MAIN_BRANCH,
    remote_name: str = POLICY_REPO_MAIN_REMOTE,
    ssh_key: Optional[str] = POLICY_REPO_SSH_KEY,
    polling_interval: int = POLICY_REPO_POLLING_INTERVAL,
    extensions: Optional[List[str]] = None,
) -> RepoWatcherTask:
    extensions = extensions if extensions is not None else OPA_FILE_EXTENSIONS
    watcher = RepoWatcher(
        repo_url=repo_url,
        clone_path=clone_path,
        branch_name=branch_name,
        remote_name=remote_name,
        ssh_key=ssh_key,
        polling_interval=polling_interval,
    )
    watcher.on_new_commits(
        partial(
            publish_changed_directories,
            publisher=publisher,
            file_extensions=extensions
        )
    )
    return RepoWatcherTask(watcher)

async def trigger_repo_watcher_pull(watcher: RepoWatcherTask, topic: Topic, data: Any):
    """
    triggers the policy watcher check for changes.
    will trigger a task on the watcher's thread.
    """
    logger.info("webhook listener triggered")
    watcher.trigger()