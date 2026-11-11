"""Start-state tests: what the server boots INTO (S2-S7 in the design spec).

The cold-empty start (S1) is covered by test_boot.py.
"""
import os
import time
from contextlib import contextmanager

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


def _orphan_sweeps(outcome: str) -> int:
    """How many looks of the orphan sweep the server logged with
    ``outcome``."""
    return compose("logs", "--no-log-prefix", "opal_server").stdout.count(
        f"outcome {outcome} ("
    )


def _give_clones_to_the_server() -> None:
    """``compose cp`` writes what it copies in as root; the server (uid 1000)
    could not remove a clone owned by root."""
    compose(
        "exec",
        "-T",
        "-u",
        "root",
        "opal_server",
        "chown",
        "-R",
        "opal:opal",
        "/opal/git_sources",
    )


@contextmanager
def _server_with(opal, **env):
    """opal_server recreated with these OPAL_TEST_* knobs (the compose file
    reads them), and recreated as it was afterwards.

    A recreate wipes the container's fs, the clones included.
    """
    before = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    compose("up", "-d", "--no-deps", "--force-recreate", "opal_server")
    opal.wait_healthy()
    try:
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        compose("up", "-d", "--no-deps", "--force-recreate", "opal_server")
        opal.wait_healthy()


_SWEEP_ON = {"OPAL_TEST_ORPHAN_SWEEP_INTERVAL": "10"}


@pytest.mark.timeout(900)
@pytest.mark.allow_worker_restart
# I1 is exempt for the sweep's timing only: the fake dir goes within two looks
# (10s apart in this test's container), not by the teardown check.
@pytest.mark.invariant_exempt("I1")
def test_orphan_clone_dir_is_reclaimed(opal):
    """Gate for the orphan sweep (OPAL_SCOPES_ORPHAN_SWEEP_INTERVAL, on for
    this test's container only): a clone dir no stored scope uses goes after
    two looks an interval apart.

    The live scope's clone beside it keeps the unused share at 0.5,
    which the default OPAL_SCOPES_ORPHAN_SWEEP_MAX_SHARE allows, and
    stays.
    """
    fake_sid = "f" * 64 + "-0"
    with _server_with(opal, **_SWEEP_ON):
        opal.put_scope("orphan-live", gitea_repo_url(list_seeded_repos(1)[0]))
        assert wait_until(
            lambda: opal.get_scope_policy("orphan-live").status_code == 200,
            timeout=300,
        ), "orphan-live never served"
        live = clone_dirs()
        compose(
            "exec",
            "-T",
            "opal_server",
            "sh",
            "-c",
            f"mkdir -p /opal/git_sources/{fake_sid} && touch /opal/git_sources/{fake_sid}/junk",
        )
        assert wait_until(
            lambda: fake_sid not in clone_dirs(), timeout=60
        ), "orphan clone dir never reclaimed by the orphan sweep"
        assert clone_dirs() >= live, "the sweep removed a live scope's clone"
        assert opal.get_scope_policy("orphan-live").status_code == 200


@pytest.mark.timeout(1500)
@pytest.mark.allow_worker_restart
@pytest.mark.invariant_exempt("I1")
def test_redis_wiped_boot_refuses_to_reclaim_clones(opal, tmp_path):
    """After a scope-store wipe the store lists no scope, which looks the same
    as a store pointed at the wrong database: the orphan sweep refuses (clones
    kept, outcome refused on every look) until a person raises
    OPAL_SCOPES_ORPHAN_SWEEP_MAX_SHARE to 1.0; then the clones go."""
    try:
        with _server_with(opal, **_SWEEP_ON):
            opal.put_scope("wipe-0", gitea_repo_url(list_seeded_repos(1)[0]))
            assert wait_until(
                lambda: opal.get_scope_policy("wipe-0").status_code == 200,
                timeout=300,
            ), "wipe-0 never served before the wipe"
            compose("stop", "opal_server")
            compose("exec", "-T", "redis", "redis-cli", "FLUSHALL")
            compose("start", "opal_server")
            opal.wait_healthy()
            wiped = clone_dirs()
            assert wiped, "the wiped scope's clone is gone before any look"
            refused = _orphan_sweeps("refused")
            assert wait_until(
                lambda: _orphan_sweeps("refused") >= refused + 3, timeout=120
            ), "the orphan sweep did not refuse three looks in a row after the wipe"
            assert clone_dirs() == wiped, "a refused sweep removed clones"
            # A person decides the scopes really are gone: the share goes to
            # 1.0. The recreate wipes the fs, so the clones go back by hand.
            compose("cp", "opal_server:/opal/git_sources", str(tmp_path / "saved"))
            with _server_with(opal, OPAL_TEST_ORPHAN_SWEEP_MAX_SHARE="1.0"):
                compose(
                    "cp",
                    str(tmp_path / "saved") + "/.",
                    "opal_server:/opal/git_sources",
                )
                _give_clones_to_the_server()
                assert wait_until(lambda: clone_dirs() == set(), timeout=60), (
                    "clones of the wiped scope store not reclaimed at a share of "
                    f"1.0: {sorted(clone_dirs())[:5]}"
                )
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
@pytest.mark.invariant_exempt("I1")
def test_boot_with_unreachable_remotes_still_serves_healthy(opal):
    """Gate for PR3's fetch timeout; green since it landed.

    Boot-time cousin of the offline gate: without the timeout, unreachable
    remotes present at boot hang the preload/first-sync clones and starve the
    executor, so a healthy scope can't serve.
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
        # safe. (Same rationale as test_redis_wiped_boot_refuses_to_reclaim_clones.)
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
    """S5: SCOPES_REPO_CLONES_SHARDS reconfig moves every source_id. Shards
    exist only with libgit2, so the reconfigured server fetches with it.
    First half: serving must survive the reshard (re-clone under new ids).
    Second half: the orphan sweep, on for this test's container, removes the
    old-shard dirs (one old and one new dir is an unused share of 0.5, which
    the default allows)."""
    from invariants import live_source_ids

    opal.put_scope("shard-0", gitea_repo_url(list_seeded_repos(1)[0]))
    assert wait_until(
        lambda: opal.get_scope_policy("shard-0").status_code == 200, timeout=300
    )
    # preserve the current shards' clones across the recreate (recreate wipes the fs)
    compose("cp", "opal_server:/opal/git_sources", str(tmp_path / "saved"))

    with _server_with(
        opal,
        OPAL_TEST_SHARDS="4",
        OPAL_TEST_FETCH_WITH_CLI="false",
        **_SWEEP_ON,
    ):
        # restore the old-shard dirs next to whatever the new boot creates
        compose("cp", str(tmp_path / "saved") + "/.", "opal_server:/opal/git_sources")
        _give_clones_to_the_server()
        opal.refresh_all()
        assert wait_until(
            lambda: opal.get_scope_policy("shard-0").status_code == 200,
            timeout=300,
        ), "scope stopped serving after the shard reconfig (first half broken!)"
        assert wait_until(
            lambda: clone_dirs() <= live_source_ids(opal, shards=4), timeout=60
        ), (
            "old-shard clone dirs not reclaimed by the orphan sweep after the "
            f"reshard: {sorted(clone_dirs())[:5]}"
        )
