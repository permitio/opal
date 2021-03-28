from typing import List
from pathlib import Path

from opal.common.paths import PathUtils
from opal.config.client.config import POLICY_SUBSCRIPTION_DIRS

def default_subscribed_policy_directories() -> List[str]:
    """
    wraps the configured value of POLICY_SUBSCRIPTION_DIRS, but dedups intersecting dirs.
    """
    subscription_directories = [Path(d) for d in POLICY_SUBSCRIPTION_DIRS]
    non_intersecting_directories = PathUtils.non_intersecting_directories(subscription_directories)
    return [str(directory) for directory in non_intersecting_directories]