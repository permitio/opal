from typing import List, Set
from pathlib import Path

from opal.client.config import POLICY_SUBSCRIPTION_DIRS

POLICY_PREFIX = "policy:"

def non_intersecting_dirs(paths: List[Path]) -> Set[Path]:
    output_paths = set()
    for candidate in paths:
        if set(candidate.parents) & output_paths:
            # the next candidate is covered by a parent which is already in output -> SKIP
            # or the next candidate is already in the list
            continue
        for out_path in list(output_paths):
            # the next candidate can displace a child from the output
            if candidate in list(out_path.parents):
                output_paths.remove(out_path)
        output_paths.add(candidate)
    return output_paths

def policy_topics(paths: List[Path]) -> List[str]:
    return ["{}{}".format(POLICY_PREFIX, str(path)) for path in paths]

def dirs_to_topics(dirs: List[str]) -> List[str]:
    policy_directories = non_intersecting_dirs([Path(d) for d in dirs])
    return policy_topics(policy_directories)

def all_policy_directories() -> List[str]:
    return non_intersecting_dirs([Path(d) for d in POLICY_SUBSCRIPTION_DIRS])