from functools import partial
from pathlib import Path
from typing import List, Optional

from git.objects import Commit
from opal_common.git.commit_viewer import CommitViewer, FileFilter, has_extension
from opal_common.git.diff_viewer import DiffViewer
from opal_common.logger import logger
from opal_common.paths import PathUtils
from opal_common.schemas.policy import (
    PolicyUpdateMessage,
    PolicyUpdateMessageNotification,
)
from opal_common.topics.publisher import TopicPublisher
from opal_common.topics.utils import policy_topics


async def create_update_all_directories_in_repo(
    old_commit: Commit,
    new_commit: Commit,
    file_extensions: Optional[List[str]] = None,
    predicate: Optional[FileFilter] = None,
) -> PolicyUpdateMessageNotification:
    """publishes policy topics matching all relevant directories in tracked
    repo, prompting the client to ask for *all* contents of these directories
    (and not just diffs)."""
    with CommitViewer(new_commit) as viewer:
        if predicate is None:
            filter = partial(has_extension, extensions=file_extensions)
        else:
            filter = predicate
        all_paths = [p.path for p in list(viewer.files(filter))]
        directories = PathUtils.intermediate_directories(all_paths)
        logger.info(
            "Publishing policy update, directories: {directories}",
            directories=[str(d) for d in directories],
        )
        topics = policy_topics(directories)
        message = PolicyUpdateMessage(
            old_policy_hash=old_commit.hexsha,
            new_policy_hash=new_commit.hexsha,
            changed_directories=[str(path) for path in directories],
        )

        return PolicyUpdateMessageNotification(topics=topics, update=message)


async def create_policy_update(
    old_commit: Commit,
    new_commit: Commit,
    file_extensions: Optional[List[str]] = None,
    predicate: Optional[FileFilter] = None,
) -> Optional[PolicyUpdateMessageNotification]:
    if new_commit == old_commit:
        return await create_update_all_directories_in_repo(
            old_commit,
            new_commit,
            file_extensions=file_extensions,
            predicate=predicate,
        )

    with DiffViewer(old_commit, new_commit) as viewer:

        def has_extension(path: Path) -> bool:
            if not file_extensions:
                return True
            return path.suffix in file_extensions

        all_paths = list(viewer.affected_paths(has_extension))
        if not all_paths:
            logger.warning(
                f"new commits detected but no tracked files were affected: '{old_commit.hexsha}' -> '{new_commit.hexsha}'",
                old_commit=old_commit,
                new_commit=new_commit,
            )
            return None
        directories = PathUtils.intermediate_directories(all_paths)
        logger.debug(
            "Generating policy update notification, directories: {directories}",
            directories=[str(d) for d in directories],
        )
        topics = policy_topics(directories)
        message = PolicyUpdateMessage(
            old_policy_hash=old_commit.hexsha,
            new_policy_hash=new_commit.hexsha,
            changed_directories=[str(path) for path in directories],
        )

        return PolicyUpdateMessageNotification(topics=topics, update=message)


async def publish_changed_directories(
    old_commit: Commit,
    new_commit: Commit,
    publisher: TopicPublisher,
    file_extensions: Optional[List[str]] = None,
):
    """publishes policy topics matching all relevant directories in tracked
    repo, prompting the client to ask for *all* contents of these directories
    (and not just diffs)."""
    notification = await create_policy_update(old_commit, new_commit, file_extensions)
    publisher.publish(topics=notification.topics, data=notification.update.dict())
