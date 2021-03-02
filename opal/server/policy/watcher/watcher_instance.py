from typing import Any
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

watcher = RepoWatcher(
    repo_url=POLICY_REPO_URL,
    clone_path=POLICY_REPO_CLONE_PATH,
    branch_name=POLICY_REPO_MAIN_BRANCH,
    remote_name=POLICY_REPO_MAIN_REMOTE,
    polling_interval=POLICY_REPO_POLLING_INTERVAL,
)
watcher.on_new_commits(partial(publish_changed_directories, file_extensions=OPA_FILE_EXTENSIONS))

repo_watcher = RepoWatcherThread(watcher)

async def trigger_webhook(topic: Topic, data: Any):
    """
    triggers the policy watcher check for changes.
    will trigger a task on the watcher's thread.
    """
    logger.info("webhook listener triggered")
    repo_watcher.trigger()