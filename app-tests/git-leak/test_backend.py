"""The bed runs the fetch backend its compose files ask for.

A run of the CLI leg on libgit2, or the reverse, fails here instead of passing
as the other backend: a git command-line clone holds only its .git directory,
a libgit2 clone a checkout too. The clone's directory is the one of its
branch's shard, so the shard count took effect as well.
"""

from helpers import (
    compose,
    fetch_backend,
    gitea_repo_url,
    list_seeded_repos,
    wait_until,
)
from invariants import BASE_DIR_IN_CONTAINER, source_id


def test_a_scope_clone_is_the_backends_clone(opal):
    url = gitea_repo_url(list_seeded_repos(1)[0])
    opal.put_scope("backend-probe", url)
    assert wait_until(
        lambda: opal.get_scope_policy("backend-probe").status_code == 200,
        timeout=300,
    ), "the probe scope never served"

    clone = f"{BASE_DIR_IN_CONTAINER}/{source_id(url)}"
    entries = compose("exec", "-T", "opal_server", "ls", "-A", clone).stdout.split()

    if fetch_backend() == "cli":
        assert entries == [".git"], f"not a git command-line clone: {entries}"
    else:
        assert (
            ".git" in entries and len(entries) > 1
        ), f"not a libgit2 clone (no checkout): {entries}"
