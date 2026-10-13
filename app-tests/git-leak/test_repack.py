"""Scope clone repack: repeated pushes must not pile up pack files.

libgit2 writes one pack file per fetch and never merges them, so without
the repack a scope clone's objects/pack dir holds one pack per fetch that
brought something, forever.
"""
import os
import re
import time
from typing import Dict, List

import pytest
from helpers import RepoMutator, compose, gitea_repo_url, wait_until
from invariants import BASE_DIR_IN_CONTAINER, source_id

# The gate's bound. opal_server runs with it for this test only (see
# OPAL_TEST_REPACK_PACK_LIMIT in docker-compose.yml): 55 pushes against the
# code default of 50 would cost more than the two container recreates.
PACK_LIMIT = 5
PUSHES = PACK_LIMIT + 5

# The limit opal_server actually runs with, default PACK_LIMIT. Set it to 0
# (repacking off) to watch the gate fail: this branch with the limit at 0
# never repacks, which for this gate is exactly origin/master's behaviour.
_SERVER_LIMIT_ENV = "REPACK_GATE_SERVER_LIMIT"
_COMPOSE_LIMIT_ENV = "OPAL_TEST_REPACK_PACK_LIMIT"

_REPO = "mutation-repack"
_SCOPE = "repack"

# GitPolicyFetcher._maybe_repack's INFO line.
_REPACK_LOG = re.compile(
    r"Repacked scope clone (?P<path>\S+) \(.*?\) in (?P<seconds>[\d.]+)s: "
    r"(?P<packs_before>\d+) packs \((?P<bytes_before>\d+) bytes\) -> "
    r"(?P<packs_after>\d+) \((?P<bytes_after>\d+) bytes\)"
)


def _pack_dir_names(sid: str) -> List[str]:
    """The names in the clone's pack dir.

    A missing dir FAILS the gate (compose raises): read as "no packs", a
    clone this test cannot see (the host-side source id not matching the
    server's, say) would pass it.
    """
    pack_dir = f"{BASE_DIR_IN_CONTAINER}/{sid}/.git/objects/pack"
    out = compose(
        "exec",
        "-T",
        "opal_server",
        "sh",
        "-c",
        f'[ -d "{pack_dir}" ] || {{ echo "no pack dir {pack_dir}" >&2; exit 3; }}; '
        f'ls -1A "{pack_dir}"',
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _settled_pack_count(sid: str, timeout: float = 60) -> int:
    """The clone's ``pack-*.pack`` count once its pack dir is quiet.

    The served hash moves as soon as the fetch lands, while the repack
    runs right after it, so a single read can catch the new pack next to
    the old ones (limit + 1). Quiet means no git temp file and two reads
    in a row agree.
    """
    deadline = time.time() + timeout
    previous = None
    names: List[str] = []
    while time.time() < deadline:
        names = _pack_dir_names(sid)
        count = sum(1 for n in names if n.startswith("pack-") and n.endswith(".pack"))
        quiet = all(n.startswith("pack-") for n in names)
        if quiet and count == previous:
            return count
        previous = count if quiet else None
        time.sleep(0.5)
    raise AssertionError(f"pack dir of {sid} never settled in {timeout}s: {names}")


def _repack_log_entries(sid: str) -> List[Dict[str, str]]:
    logs = compose("logs", "--no-log-prefix", "opal_server").stdout
    return [m.groupdict() for m in _REPACK_LOG.finditer(logs) if sid in m.group("path")]


def _served_hash(opal) -> str:
    return opal.get_scope_policy(_SCOPE).json().get("hash")


def _recreate_opal_server(opal) -> float:
    started = time.monotonic()
    compose("up", "-d", "--no-deps", "--force-recreate", "opal_server")
    opal.wait_healthy()
    return time.monotonic() - started


@pytest.mark.timeout(1200)
@pytest.mark.allow_worker_restart
def test_pushes_keep_pack_count_bounded(opal, gitea_admin, tmp_path):
    """Push PUSHES commits, refreshing after each: the clone must never hold
    more than PACK_LIMIT packs, and the scope must serve the last push.

    And the bound must have been EARNED: the count starts at the clone's own
    pack, builds up to the limit and drops back, and the server logged at
    least one repack of this clone that ended at one pack. Without those, a
    clone whose fetches stop writing packs (or that this test is not looking
    at) would pass the bound vacuously, here and on origin/master alike.
    """
    server_limit = os.environ.get(_SERVER_LIMIT_ENV, str(PACK_LIMIT))
    previous_limit = os.environ.get(_COMPOSE_LIMIT_ENV)
    sid = source_id(gitea_repo_url(_REPO))
    os.environ[_COMPOSE_LIMIT_ENV] = server_limit
    try:
        up_seconds = _recreate_opal_server(opal)
        print(f"\n[repack gate] limit {server_limit}: up in {up_seconds:.1f}s")

        gitea_admin.create_repo(_REPO)
        opal.put_scope(_SCOPE, gitea_repo_url(_REPO))
        assert wait_until(
            lambda: opal.get_scope_policy(_SCOPE).status_code == 200, timeout=300
        ), "scope never served its first clone"

        counts = [_settled_pack_count(sid)]
        mutator = RepoMutator(_REPO, tmp_path)
        loop_started = time.monotonic()
        for push in range(1, PUSHES + 1):
            sha = mutator.push_file("data.json", f'{{"push": {push}}}\n')
            opal.refresh_all()
            assert wait_until(
                lambda sha=sha: _served_hash(opal) == sha, timeout=120, interval=0.5
            ), f"push {push} ({sha}) never served after a refresh"
            counts.append(_settled_pack_count(sid))
        loop_seconds = time.monotonic() - loop_started
        print(
            f"[repack gate] {PUSHES} pushes in {loop_seconds:.1f}s; pack count "
            f"after the clone and after each refresh: {counts} (max {max(counts)})"
        )
        repacks = _repack_log_entries(sid)
        for entry in repacks:
            print(
                f"[repack gate] repack: {entry['seconds']}s, "
                f"{entry['packs_before']} packs ({entry['bytes_before']} bytes) -> "
                f"{entry['packs_after']} ({entry['bytes_after']} bytes)"
            )

        bundle = opal.get_scope_policy(_SCOPE).json()
        assert bundle["hash"] == sha, "the scope does not serve the last push"
        assert [m["data"] for m in bundle["data_modules"]] == [
            f'{{"push": {PUSHES}}}\n'
        ], "the served bundle does not hold the last push's data.json"
        assert max(counts) <= PACK_LIMIT, (
            f"the clone's pack count went over {PACK_LIMIT}: {counts} "
            "(without the repack it grows by one per fetch)"
        )
        assert counts[0] >= 1, f"the clone of {sid} holds no pack: {counts}"
        peak = counts.index(max(counts))
        assert max(counts) >= PACK_LIMIT - 1 and min(counts[peak:]) < max(counts), (
            f"the pack count never built up to the limit and dropped: {counts} "
            "(are the fetches still writing packs?)"
        )
        assert repacks, f"the server log has no repack of {sid}"
        assert all(
            e["packs_after"] == "1" and int(e["packs_before"]) >= PACK_LIMIT
            for e in repacks
        ), f"a repack of {sid} did not merge the limit's packs into one: {repacks}"
    finally:
        # The default limit comes back FIRST: a failure in the cleanup below
        # (the server down, say) must not leave every later gate running at
        # this test's limit.
        if previous_limit is None:
            os.environ.pop(_COMPOSE_LIMIT_ENV, None)
        else:
            os.environ[_COMPOSE_LIMIT_ENV] = previous_limit
        try:
            try:
                # Before the recreate, as opal_multiworker does: a scope still
                # in the store would have the restored server clone it again.
                opal.delete_scope(_SCOPE)
            finally:
                down_seconds = _recreate_opal_server(opal)
                print(f"[repack gate] opal_server restored in {down_seconds:.1f}s")
        finally:
            gitea_admin.delete_repo(_REPO)
