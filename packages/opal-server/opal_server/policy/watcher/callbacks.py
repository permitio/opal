from functools import partial
from pathlib import Path
from typing import List, Optional

from git import Repo
from git.objects import Commit
from opal_common.async_utils import run_sync
from opal_common.git_utils.commit_viewer import (
    CommitViewer,
    FileFilter,
    find_ignore_match,
    has_extension,
)
from opal_common.git_utils.diff_viewer import DiffViewer
from opal_common.logger import logger
from opal_common.paths import PathUtils
from opal_common.schemas.policy import (
    PolicyUpdateMessage,
    PolicyUpdateMessageNotification,
)
from opal_common.topics.publisher import TopicPublisher
from opal_common.topics.utils import policy_topics


def create_update_all_directories_in_repo(
    old_commit: Commit,
    new_commit: Commit,
    file_extensions: Optional[List[str]] = None,
    bundle_ignore: Optional[List[str]] = None,
    predicate: Optional[FileFilter] = None,
) -> PolicyUpdateMessageNotification:
    """Publishes policy topics matching all relevant directories in tracked
    repo, prompting the client to ask for *all* contents of these directories
    (and not just diffs).

    Blocking: it walks the commit's whole tree through git processes.
    """
    with CommitViewer(new_commit) as viewer:
        if predicate is None:
            _has_extension = partial(has_extension, extensions=file_extensions)
            _find_ignore_match = partial(find_ignore_match, bundle_ignore=bundle_ignore)
            filter = lambda f: _has_extension(f) and _find_ignore_match(f.path) == None
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


def create_policy_update(
    old_commit: Commit,
    new_commit: Commit,
    file_extensions: Optional[List[str]] = None,
    bundle_ignore: Optional[List[str]] = None,
    predicate: Optional[FileFilter] = None,
) -> Optional[PolicyUpdateMessageNotification]:
    """The notification of what changed between two commits; blocking: it diffs
    them (or walks the tree, for one commit) through git processes."""
    if new_commit == old_commit:
        return create_update_all_directories_in_repo(
            old_commit,
            new_commit,
            file_extensions=file_extensions,
            bundle_ignore=bundle_ignore,
            predicate=predicate,
        )

    with DiffViewer(old_commit, new_commit) as viewer:

        def is_path_affected(path: Path) -> bool:
            if not file_extensions:
                return True
            if not path.suffix in file_extensions:
                return False
            return find_ignore_match(path, bundle_ignore) is None

        all_paths = list(viewer.affected_paths(is_path_affected))
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


def _policy_update_in_a_repo_of_its_own(
    git_dir: str,
    old_sha: str,
    new_sha: str,
    file_extensions: Optional[List[str]],
    bundle_ignore: Optional[List[str]],
) -> Optional[PolicyUpdateMessageNotification]:
    """create_policy_update on a Repo opened for this call alone, closed once
    the notification is built."""
    with Repo(git_dir) as repo:
        return create_policy_update(
            repo.commit(old_sha), repo.commit(new_sha), file_extensions, bundle_ignore
        )


async def publish_changed_directories(
    old_commit: Commit,
    new_commit: Commit,
    publisher: TopicPublisher,
    file_extensions: Optional[List[str]] = None,
    bundle_ignore: Optional[List[str]] = None,
):
    """Publishes policy topics matching all relevant directories in tracked
    repo, prompting the client to ask for *all* contents of these directories
    (and not just diffs)."""
    # On a thread: it diffs the commits (or walks the tree) through git
    # processes for as long as the diff or the tree is large. On a Repo of its
    # own: the watcher's (and its git cat-file processes) stays the loop's,
    # which a webhook's pull may be using meanwhile.
    notification = await run_sync(
        _policy_update_in_a_repo_of_its_own,
        new_commit.repo.git_dir,
        old_commit.hexsha,
        new_commit.hexsha,
        file_extensions,
        bundle_ignore,
    )

    if notification:
        async with publisher:
            await publisher.publish(
                topics=notification.topics, data=notification.update.model_dump()
            )
