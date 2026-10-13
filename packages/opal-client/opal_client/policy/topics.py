from pathlib import Path
from typing import List

from opal_client.config import opal_client_config
from opal_common.paths import PathUtils


def resolve_policy_source_ids(single_source_id=None, source_ids=None) -> List[str]:
    if single_source_id and source_ids:
        raise ValueError(
            "Configure either POLICY_SOURCE_ID or POLICY_SOURCE_IDS, not both"
        )

    selected_ids = [single_source_id] if single_source_id else source_ids or []
    selected_ids = [source_id.strip() for source_id in selected_ids]
    if any(not source_id for source_id in selected_ids):
        raise ValueError("Policy source IDs must not be empty")
    if any(
        not source_id[0].isascii()
        or not source_id[0].isalnum()
        or not all(
            character.isascii() and (character.isalnum() or character in "-_")
            for character in source_id
        )
        for source_id in selected_ids
    ):
        raise ValueError(
            "Policy source IDs may contain only letters, digits, '-' or '_'"
        )
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Policy source IDs must be unique")
    return selected_ids


def default_subscribed_policy_directories(directories=None) -> List[str]:
    """Wraps the configured value of POLICY_SUBSCRIPTION_DIRS, but dedups
    intersecting dirs."""
    subscription_directories = [
        Path(d)
        for d in (
            opal_client_config.POLICY_SUBSCRIPTION_DIRS
            if directories is None
            else directories
        )
    ]
    non_intersecting_directories = PathUtils.non_intersecting_directories(
        subscription_directories
    )
    return [str(directory) for directory in non_intersecting_directories]
