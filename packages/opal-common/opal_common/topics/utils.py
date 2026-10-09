from pathlib import Path
from typing import List

from opal_common.paths import PathUtils

POLICY_PREFIX = "policy:"


def policy_topics(paths: List[Path], source_id: str = None) -> List[str]:
    """Prefixes a list of directories with the policy topic prefix."""
    source_prefix = f"{source_id}:" if source_id else ""
    return ["{}{}{}".format(POLICY_PREFIX, source_prefix, str(path)) for path in paths]


def remove_prefix(topic: str, prefix: str = POLICY_PREFIX):
    """Removes the policy topic prefix to get the path (directory) encoded in
    the topic."""
    if topic.startswith(prefix):
        return topic[len(prefix) :]
    return topic


def pubsub_topics_from_directories(
    dirs: List[str], source_id: str = None
) -> List[str]:
    """Converts a list of directories on the policy repository that the client
    wants to subscribe to into a list of topics.

    this method also ensures the client only subscribes to non-
    intersecting directories by dedupping directories that are
    descendents of one another.
    """
    policy_directories = PathUtils.non_intersecting_directories([Path(d) for d in dirs])
    return policy_topics(policy_directories, source_id=source_id)


def pubsub_topics_from_sources(
    dirs: List[str], source_ids: List[str]
) -> List[str]:
    return [
        topic
        for source_id in source_ids
        for topic in pubsub_topics_from_directories(dirs, source_id=source_id)
    ]
