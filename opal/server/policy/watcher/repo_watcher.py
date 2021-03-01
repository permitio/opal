from typing import List
from pathlib import Path
from functools import partial
from git.objects import Commit

from opal.common.paths import PathUtils
from opal.common.logger import get_logger
from opal.common.git.commit_viewer import CommitViewer, has_extension
from opal.common.git.diff_viewer import DiffViewer
from opal.common.git.repo_watcher import RepoWatcher
from opal.server.config import (
    POLICY_REPO_URL,
    POLICY_REPO_CLONE_PATH,
    POLICY_REPO_MAIN_BRANCH,
    POLICY_REPO_MAIN_REMOTE,
    POLICY_REPO_POLLING_INTERVAL,
    OPA_FILE_EXTENSIONS,
)
from opal.server.policy.publisher import policy_publisher

logger = get_logger("opal.git.watcher")


def policy_topics(paths: List[Path]) -> List[str]:
    return ["policy:{}".format(str(path)) for path in paths]


async def publish_full_manifest(
    old_commit: Commit, new_commit: Commit, file_extensions: List[str] = OPA_FILE_EXTENSIONS):
    """
    publishes policy topics matching all relevant directories in tracked repo,
    prompting the client to ask for *all* contents of these directories (and not just diffs).
    """
    with CommitViewer(new_commit) as viewer:
        filter = partial(has_extension, extensions=file_extensions)
        all_paths = list(viewer.files(filter))
        directories = PathUtils.intermediate_directories(all_paths)
        logger.info("Publishing policy update", directories=[str(d) for d in directories])
        topics = policy_topics(directories)
        policy_publisher.publish_updates(topics=topics, data=new_commit.hexsha)

async def publish_changed_directories(
    old_commit: Commit, new_commit: Commit, file_extensions: List[str] = OPA_FILE_EXTENSIONS):
    """
    publishes policy topics matching all relevant directories in tracked repo,
    prompting the client to ask for *all* contents of these directories (and not just diffs).
    """
    if new_commit == old_commit:
        return await publish_full_manifest(old_commit, new_commit, file_extensions=file_extensions)

    with DiffViewer(old_commit, new_commit) as viewer:
        def has_extension(path: Path) -> bool:
            if not file_extensions:
                return True
            return path.suffix in file_extensions
        all_paths = list(viewer.affected_paths(has_extension))
        if not all_paths:
            logger.warn("new commits detected but no files are affected", old_commit=old_commit, new_commit=new_commit)
            return
        directories = PathUtils.intermediate_directories(all_paths)
        logger.info("Publishing policy update", directories=[str(d) for d in directories])
        topics = policy_topics(directories)
        policy_publisher.publish_updates(topics=topics, data=new_commit.hexsha)


policy_watcher = RepoWatcher(
    repo_url=POLICY_REPO_URL,
    clone_path=POLICY_REPO_CLONE_PATH,
    branch_name=POLICY_REPO_MAIN_BRANCH,
    remote_name=POLICY_REPO_MAIN_REMOTE,
    polling_interval=POLICY_REPO_POLLING_INTERVAL,
)

policy_watcher.on_new_commits(publish_changed_directories)

async def trigger_webhook(topic, data):
    """
    triggers the policy watcher check for changes.
    will trigger a task on the watcher's thread.
    """
    logger.info("webhook listener triggered")
    policy_watcher.trigger()