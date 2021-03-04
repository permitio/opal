from opal.common.communication.topic_publisher import TopicPublisherThread
from typing import Any, Optional, List
from functools import partial

from fastapi_websocket_pubsub import Topic
from opal.common.logger import get_logger
from opal.common.git.repo_watcher import RepoWatcher
from opal.server.config import (
    POLICY_REPO_URL,
    POLICY_REPO_CLONE_PATH,
    POLICY_REPO_MAIN_BRANCH,
    POLICY_REPO_MAIN_REMOTE,
    POLICY_REPO_POLLING_INTERVAL,
    OPA_FILE_EXTENSIONS,
)
from opal.server.policy.watcher.watcher_thread import RepoWatcherThread
from opal.server.policy.watcher.watcher_callbacks import publish_changed_directories

logger = get_logger("opal.git.watcher.thread")


def setup_watcher_thread(
    publisher: TopicPublisherThread,
    repo_url: str = POLICY_REPO_URL,
    clone_path: str = POLICY_REPO_CLONE_PATH,
    branch_name: str = POLICY_REPO_MAIN_BRANCH,
    remote_name: str = POLICY_REPO_MAIN_REMOTE,
    polling_interval: int = POLICY_REPO_POLLING_INTERVAL,
    extensions: Optional[List[str]] = None,
) -> RepoWatcherThread:
    extensions = extensions if extensions is not None else OPA_FILE_EXTENSIONS
    watcher = RepoWatcher(
        repo_url=repo_url,
        clone_path=clone_path,
        branch_name=branch_name,
        remote_name=remote_name,
        polling_interval=polling_interval,
    )
    watcher.on_new_commits(
        partial(
            publish_changed_directories,
            publisher=publisher,
            file_extensions=extensions
        )
    )
    return RepoWatcherThread(watcher)

async def trigger_repo_watcher_pull(watcher: RepoWatcherThread, topic: Topic, data: Any):
    """
    triggers the policy watcher check for changes.
    will trigger a task on the watcher's thread.
    """
    logger.info("webhook listener triggered")
    watcher.trigger()