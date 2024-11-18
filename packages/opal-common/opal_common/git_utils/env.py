import os
from pathlib import Path

from opal_common.config import opal_common_config

SSH_PREFIX = "ssh://"
GIT_SSH_USER_PREFIX = "git@"


def save_ssh_key_to_pem_file(key: str) -> Path:
    key = key.replace("_", "\n")
    if not key.endswith("\n"):
        key = key + "\n"  # pem file must end with newline
    key_path = os.path.expanduser(opal_common_config.GIT_SSH_KEY_FILE)
    parent_directory = os.path.dirname(key_path)
    if not os.path.exists(parent_directory):
        os.makedirs(parent_directory, exist_ok=True)
    with open(key_path, "w") as f:
        f.write(key)
    os.chmod(key_path, 0o600)
    return Path(key_path)


def is_ssh_repo_url(repo_url: str):
    """Return True if the repo url uses SSH authentication.

    (see:
    https://docs.github.com/en/github/authenticating-to-github/connecting-to-github-with-ssh)
    """
    return repo_url.startswith(SSH_PREFIX) or repo_url.startswith(GIT_SSH_USER_PREFIX)


def provide_git_ssh_environment(url: str, ssh_key: str):
    """Provides git SSH configuration via GIT_SSH_COMMAND.

    the git ssh config will be provided only if the following conditions are met:
    - the repo url is a git ssh url
    - an ssh private key is provided in Repo Cloner __init__
    """
    if not is_ssh_repo_url(url) or ssh_key is None:
        return {}  # no ssh config
    git_ssh_identity_file = save_ssh_key_to_pem_file(ssh_key)
    return {
        "GIT_SSH_COMMAND": f"ssh -o StrictHostKeyChecking=no -o IdentitiesOnly=yes -i {git_ssh_identity_file}",
        "GIT_TRACE": "1",
        "GIT_CURL_VERBOSE": "1",
    }
