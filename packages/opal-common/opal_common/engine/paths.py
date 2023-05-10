from pathlib import Path

from opal_common.config import opal_common_config


def is_data_module(path: Path) -> bool:
    """Only json files named `data.json` can be included in official OPA
    bundles as static data files.

    checks if a given path points to such file.
    """
    return path.name == "data.json"


def is_policy_module(path: Path) -> bool:
    """Checks if a given path points to a rego file (extension == .rego).

    Only rego files are allowed in official OPA bundles as policy files.
    """
    return path.suffix in opal_common_config.POLICY_REPO_POLICY_EXTENSIONS
