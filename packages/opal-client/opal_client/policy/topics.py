from pathlib import Path
from typing import List

from opal_client.config import opal_client_config
from opal_common.paths import PathUtils


def default_subscribed_policy_directories() -> List[str]:
    """wraps the configured value of POLICY_SUBSCRIPTION_DIRS, but dedups
    intersecting dirs."""
    subscription_directories = [
        Path(d) for d in opal_client_config.POLICY_SUBSCRIPTION_DIRS
    ]
    non_intersecting_directories = PathUtils.non_intersecting_directories(
        subscription_directories
    )
    return [str(directory) for directory in non_intersecting_directories]
