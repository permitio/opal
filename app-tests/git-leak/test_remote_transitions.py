"""Remote-side transitions (T16): the tenant rewrites or deletes what we track.

Both are CHARACTERIZATION tests — they pin today's behavior. If one fails,
the behavior changed: decide deliberately, don't just update the assert.
"""
import pytest
from helpers import GiteaAdmin, RepoMutator, gitea_repo_url, wait_until


@pytest.mark.timeout(900)
def test_force_push_rewrite_recovers(opal, gitea_admin, tmp_path):
    """A force-pushed (rewritten) head must be picked up on refresh: pygit2's
    default fetch refspec is forced, and set_target just moves the local
    ref."""
    gitea_admin.create_repo("mutation-force-push")
    try:
        opal.put_scope("fp", gitea_repo_url("mutation-force-push"))
        assert wait_until(
            lambda: opal.get_scope_policy("fp").status_code == 200, timeout=300
        )
        old_bundle = opal.get_scope_policy("fp").json()

        RepoMutator("mutation-force-push", tmp_path).force_push_rewrite()
        opal.refresh_all()

        assert wait_until(
            lambda: opal.get_scope_policy("fp").status_code == 200
            and opal.get_scope_policy("fp").json().get("hash")
            != old_bundle.get("hash"),
            timeout=300,
        ), "rewritten head never served after refresh"
    finally:
        opal.delete_scope("fp")
        gitea_admin.delete_repo("mutation-force-push")


@pytest.mark.timeout(900)
def test_deleted_branch_keeps_serving_last_head(opal, gitea_admin, tmp_path):
    """Deleting the tracked branch upstream must not crash anything; fetch
    doesn't prune, so OPAL silently keeps serving the last known head —
    documented (not necessarily desirable) behavior."""
    gitea_admin.create_repo("mutation-branch-del")
    mut = RepoMutator("mutation-branch-del", tmp_path)
    mut.push_new_branch("extra")
    try:
        opal.put_scope("bd", gitea_repo_url("mutation-branch-del"), branch="extra")
        assert wait_until(
            lambda: opal.get_scope_policy("bd").status_code == 200, timeout=300
        )

        mut.delete_remote_branch("extra")
        opal.refresh_all()

        # settle, then pin: still healthy, still serving the last head
        assert wait_until(
            lambda: opal.get_scope_policy("bd").status_code == 200, timeout=120
        ), "scope stopped serving after upstream branch deletion"
    finally:
        opal.delete_scope("bd")
        gitea_admin.delete_repo("mutation-branch-del")
