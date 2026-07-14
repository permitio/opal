"""Start-state tests: what the server boots INTO (S2-S7 in the design spec).

The cold-empty start (S1) is covered by test_boot.py.
"""
import time

import pytest
from helpers import (
    HEALTHY_PROBE_REPO,
    compose,
    gitea_repo_url,
    list_seeded_repos,
    make_repo_unreachable,
    wait_until,
)
from invariants import clone_dirs


def _clone_log_count() -> int:
    return compose("logs", "--no-log-prefix", "opal_server").stdout.count(
        "Cloning repo"
    )


@pytest.mark.timeout(900)
@pytest.mark.allow_worker_restart
def test_warm_boot_reuses_clones(opal, repo_count):
    """A restart with intact clones must serve without re-cloning (S2)."""
    n = min(repo_count, 10)
    for i, repo in enumerate(list_seeded_repos(n)):
        opal.put_scope(f"warm-{i}", gitea_repo_url(repo))
    for i in range(n):
        assert wait_until(
            lambda i=i: opal.get_scope_policy(f"warm-{i}").status_code == 200,
            timeout=600,
        ), f"warm-{i} never served before the restart"

    clones_before = _clone_log_count()
    compose("restart", "opal_server")
    opal.wait_healthy()

    for i in range(n):
        assert wait_until(
            lambda i=i: opal.get_scope_policy(f"warm-{i}").status_code == 200,
            timeout=300,
        ), f"warm-{i} not served after warm restart"
    assert (
        _clone_log_count() == clones_before
    ), "warm boot re-cloned instead of reusing the on-disk clones"


@pytest.mark.timeout(900)
def test_corrupt_clone_recovers_without_clone_loop(opal):
    """S3/T7: emptying a clone's object store in place (objects/ kept as an
    empty dir, so pygit2.discover_repository still finds the repo) while the
    server holds a warm cached handle must be detected as invalid (gutted
    object store: refs intact, head object unreadable) and recover through
    the invalid-repo branch with exactly one re-clone — no serve-500s-
    forever wedge and no re-clone loop."""
    repo = list_seeded_repos(3)[2]
    opal.put_scope("dirty", gitea_repo_url(repo))
    assert wait_until(
        lambda: opal.get_scope_policy("dirty").status_code == 200, timeout=300
    )

    invalid_before = compose("logs", "--no-log-prefix", "opal_server").stdout.count(
        "Deleting invalid repo"
    )

    # empty the object store's CONTENTS in place, keeping the objects/ dir
    # itself so discover_repository still resolves the repo; the server keeps
    # its cached pygit2 handle (warm cache) — the gutted-object-store case
    # (deleting the objects/ node instead would route recovery through the
    # repo-not-found -> _clone() branch and never touch the cached handle)
    compose(
        "exec",
        "-T",
        "opal_server",
        "sh",
        "-c",
        'for d in /opal/git_sources/*/; do rm -rf "$d/.git/objects"/*; done',
    )
    opal.refresh_all()

    assert wait_until(
        lambda: opal.get_scope_policy("dirty").status_code == 200, timeout=300
    ), "scope never recovered after clone corruption"

    invalid_after = compose("logs", "--no-log-prefix", "opal_server").stdout.count(
        "Deleting invalid repo"
    )
    assert invalid_after > invalid_before, (
        "recovery did not take the invalid-repo (warm cached handle) branch — "
        "the corruption failed to exercise the Bug A path"
    )

    clones_1 = _clone_log_count()
    opal.refresh_all()
    time.sleep(10)
    clones_2 = _clone_log_count()
    assert clones_2 == clones_1, (
        f"re-clone loop: clone count kept growing after recovery "
        f"({clones_1} -> {clones_2})"
    )


@pytest.mark.timeout(900)
@pytest.mark.invariant_exempt("I1")
def test_orphan_clone_dir_is_reclaimed(opal):
    """RED until an orphan sweep exists (PR3+, currently unowned): a clone dir
    with no live scope must eventually be removed."""
    fake_sid = "f" * 64 + "-0"
    compose(
        "exec",
        "-T",
        "opal_server",
        "sh",
        "-c",
        f"mkdir -p /opal/git_sources/{fake_sid} && touch /opal/git_sources/{fake_sid}/junk",
    )
    try:
        opal.refresh_all()
        assert wait_until(
            lambda: fake_sid not in clone_dirs(), timeout=60
        ), "orphan clone dir never reclaimed (needs an orphan sweep)"
    finally:
        # red gate leaves state on purpose; clean it so later tests' I1 holds
        compose(
            "exec",
            "-T",
            "opal_server",
            "sh",
            "-c",
            f"rm -rf /opal/git_sources/{fake_sid}",
        )


@pytest.mark.timeout(900)
@pytest.mark.allow_worker_restart
@pytest.mark.invariant_exempt("I1")
def test_redis_wiped_boot_reclaims_clones(opal):
    """RED until the orphan sweep (same class as the orphan-dir gate): after a
    scope-store wipe, on-disk clones reference nothing and must be
    reclaimed."""
    opal.put_scope("wipe-0", gitea_repo_url(list_seeded_repos(1)[0]))
    assert wait_until(
        lambda: opal.get_scope_policy("wipe-0").status_code == 200, timeout=300
    ), "wipe-0 never served before the wipe"
    try:
        compose("stop", "opal_server")
        compose("exec", "-T", "redis", "redis-cli", "FLUSHALL")
        compose("start", "opal_server")
        opal.wait_healthy()
        assert wait_until(
            lambda: clone_dirs() == set(), timeout=60
        ), f"clones of the wiped scope store never reclaimed: {sorted(clone_dirs())[:5]}"
    finally:
        opal.hard_reset()
        # hard_reset never touches git_sources/, and post-FLUSHALL no scope
        # record exists to route a DELETE's rmtree at the leftover clone —
        # remove it explicitly so later tests' I1 stays meaningful. The scope
        # store is empty here, so a blanket clean is safe.
        compose(
            "exec",
            "-T",
            "opal_server",
            "sh",
            "-c",
            "rm -rf /opal/git_sources/*",
        )


@pytest.mark.timeout(1200)
@pytest.mark.allow_worker_restart
@pytest.mark.invariant_exempt("I1", "I3", "I4")
def test_boot_with_unreachable_remotes_still_serves_healthy(opal):
    """RED until PR3 (fetch timeout) — WATCH THIS FLIP when PR3 merges.

    Boot-time cousin of the offline gate: unreachable remotes present at boot
    hang the preload/first-sync clones and starve the executor, so a healthy
    scope can't serve.
    """
    for i in range(10):
        opal.put_scope(f"down-{i}", make_repo_unreachable(f"down-{i}-repo"))
    opal.put_scope("boot-healthy", gitea_repo_url(HEALTHY_PROBE_REPO))
    try:
        compose("restart", "opal_server")
        opal.wait_healthy(timeout=300)
        assert wait_until(
            lambda: opal.get_scope_policy("boot-healthy").status_code == 200,
            timeout=300,
        ), "healthy scope starved at boot by unreachable remotes (PR3 gate)"
    finally:
        opal.hard_reset()
        # hard_reset flushes Redis but never touches git_sources/ — the
        # blackhole scopes' partial clone dirs would poison later tests' I1
        # checks. The scope store is empty post-reset, so a blanket clean is
        # safe. (Same rationale as test_redis_wiped_boot_reclaims_clones.)
        compose(
            "exec",
            "-T",
            "opal_server",
            "sh",
            "-c",
            "rm -rf /opal/git_sources/*",
        )


@pytest.mark.timeout(1200)
@pytest.mark.allow_worker_restart
@pytest.mark.invariant_exempt("I1")
def test_shard_reconfig_still_serves_but_orphans_old_clones(opal, tmp_path):
    """S5: SCOPES_REPO_CLONES_SHARDS reconfig moves every source_id.
    GREEN half: serving must survive the reshard (re-clone under new ids).
    RED half (until the orphan sweep): the old-shard dirs are orphaned."""
    import os

    from invariants import live_source_ids

    opal.put_scope("shard-0", gitea_repo_url(list_seeded_repos(1)[0]))
    assert wait_until(
        lambda: opal.get_scope_policy("shard-0").status_code == 200, timeout=300
    )
    # preserve the shards=1 clones across the recreate (recreate wipes the fs)
    compose("cp", "opal_server:/opal/git_sources", str(tmp_path / "saved"))

    os.environ["OPAL_TEST_SHARDS"] = "4"
    try:
        compose("up", "-d", "--no-deps", "--force-recreate", "opal_server")
        opal.wait_healthy()
        # restore the old-shard dirs next to whatever the new boot creates
        compose("cp", str(tmp_path / "saved") + "/.", "opal_server:/opal/git_sources")
        opal.refresh_all()
        assert wait_until(
            lambda: opal.get_scope_policy("shard-0").status_code == 200,
            timeout=300,
        ), "scope stopped serving after the shard reconfig (green half broken!)"
        assert wait_until(
            lambda: clone_dirs() <= live_source_ids(opal, shards=4), timeout=60
        ), (
            "old-shard clone dirs orphaned after reshard (red half — orphan "
            f"sweep gate): {sorted(clone_dirs())[:5]}"
        )
    finally:
        os.environ["OPAL_TEST_SHARDS"] = "1"
        compose("up", "-d", "--no-deps", "--force-recreate", "opal_server")
        opal.wait_healthy()
