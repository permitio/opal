from pathlib import Path
from typing import List

from opal_common.paths import PathUtils

POLICY_PREFIX = "policy:"


def policy_topics(paths: List[Path]) -> List[str]:
    """prefixes a list of directories with the policy topic prefix."""
    return ["{}{}".format(POLICY_PREFIX, str(path)) for path in paths]


def remove_prefix(topic: str, prefix: str = POLICY_PREFIX):
    """removes the policy topic prefix to get the path (directory) encoded in
    the topic."""
    if topic.startswith(prefix):
        return topic[len(prefix) :]
    return topic


def pubsub_topics_from_directories(dirs: List[str]) -> List[str]:
    """converts a list of directories on the policy repository that the client
    wants to subscribe to into a list of topics.

    this method also ensures the client only subscribes to non-
    intersecting directories by dedupping directories that are
    decendents of one another.
    """
    policy_directories = PathUtils.non_intersecting_directories([Path(d) for d in dirs])
    return policy_topics(policy_directories)
