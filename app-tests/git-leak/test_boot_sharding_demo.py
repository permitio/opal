"""Demo: SHARDS caps the prod-dominant boot shape, not SCOPES_GIT_MAX_WORKERS.

NOT part of the normal bed pass — gated behind RUN_SHARDS_DEMO=1 (see the
skipif below) so a plain `pytest` run of this directory never collects it
for real.

Design finding this demonstrates: prod's dominant boot shape is ONE shared
repo with MANY branches (one team's policy repo, one branch per
environment/tenant) — not the many-distinct-repos shape test_boot.py
measures. All those branches share a single git URL, so
GitPolicyFetcher.source_id (sha256(url) + sha256(branch)[0] % SHARDS)
collapses them onto SCOPES_REPO_CLONES_SHARDS distinct clone dirs/locks, and
ScopesService.sync_scopes partitions scopes by that same source_id: only
the first scope touching each distinct source_id takes the network
clone/fetch path (bounded by SCOPES_GIT_MAX_WORKERS); every other scope on
that source_id is a "duplicate" that still has to check out its own branch
against the SAME on-disk clone, serialized behind that source_id's
per-repository lock (pygit2 handles are not thread-safe — see
git_fetcher.py's ``_git_busy`` set). With SHARDS=1 every branch collapses to
one lock and the whole boot serializes on it, no matter how high
SCOPES_GIT_MAX_WORKERS is set. Raising SHARDS is what actually buys
parallelism for this shape.

Run the sweep from the host, one SHARDS value per invocation (the compose
file's `OPAL_SCOPES_REPO_CLONES_SHARDS: "${OPAL_TEST_SHARDS:-1}"` env
interpolation means a changed OPAL_TEST_SHARDS is a config diff `docker
compose up` picks up on its own; this test also does its own
--force-recreate right before timing, mirroring test_boot.py, so the clock
always starts at a deterministic cold boot):

    cd app-tests/git-leak
    OPAL_TEST_SHARDS=1  MAIN_REPO_BRANCHES=200 RUN_SHARDS_DEMO=1 \\
        <venv>/bin/python -m pytest test_boot_sharding_demo.py -v -s
    OPAL_TEST_SHARDS=3  MAIN_REPO_BRANCHES=200 RUN_SHARDS_DEMO=1 \\
        <venv>/bin/python -m pytest test_boot_sharding_demo.py -v -s
    OPAL_TEST_SHARDS=10 MAIN_REPO_BRANCHES=200 RUN_SHARDS_DEMO=1 \\
        <venv>/bin/python -m pytest test_boot_sharding_demo.py -v -s

The stack must already have been brought up once with
MAIN_REPO_BRANCHES=200 so the `shared-policy` repo and its branches exist
(see docker-compose.yml's seed-service env and seed/seed_gitea.py's
main-tier seed mode).
"""
import os
import re
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
from helpers import compose, gitea_repo_url

RUN_DEMO = os.environ.get("RUN_SHARDS_DEMO") == "1"

# Strips loguru's ANSI colorization (LOG_COLORIZE defaults True and loguru
# writes real escape codes even to a piped, non-tty sink) so timestamp/marker
# parsing below doesn't have to fight embedded color codes.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# All the markers this module parses (preload/sync_scopes activity: "Cloning
# repo at", "Clone completed", "Created local branch") are logged from
# ``ScopesPolicyWatcherTask.preload_scopes()``, which runs synchronously in
# the gunicorn MASTER process BEFORE it forks workers and BEFORE the app's
# own ``configure_logs()`` (which installs opal_common's custom LOG_FORMAT)
# has run — so these lines use loguru's built-in DEFAULT sink format instead:
# "2026-07-28 00:37:24.481 | INFO     | opal_server.git_fetcher:_clone:622 -
# Cloning repo at ...". Space-separated, millisecond precision, no tz offset
# (naive; the container clock is UTC). Any post-fork request-time log (the
# app's real LOG_FORMAT, ISO ``T``-separated with a tz offset, optionally
# ANSI-colorized) is tried as a fallback in case that ever changes.
_TS_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f%z")


def _fmt(value) -> str:
    return f"{value:.2f}" if isinstance(value, (int, float)) else "NA"


def _parse_log_line_ts(line: str):
    clean = _ANSI_RE.sub("", line)
    ts_str = clean.split("|", 1)[0].strip()
    for fmt in _TS_FORMATS:
        try:
            ts = datetime.strptime(ts_str, fmt)
            # Normalize to naive UTC: the preload-time lines this module
            # actually cares about are already naive (container clock is
            # UTC); stripping tzinfo off the ISO fallback format keeps every
            # parsed timestamp comparable to every other one.
            if ts.tzinfo is not None:
                ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
            return ts
        except ValueError:
            continue
    return None


def _log_breakdown(shards: int, k: int, since_epoch: float) -> dict:
    """Parse `docker compose logs opal_server` (since the force-recreate that
    started this boot) into a phase-1 (clone) vs phase-2 (local branch
    checkout) time breakdown.

    Boundary rationale (see module docstring): ``sync_scopes`` runs phase 1
    (one clone/fetch per distinct source_id — exactly ``shards`` of them,
    the "unique" scopes) to full completion — via a single ``await`` on their
    ``asyncio.gather`` — before phase 2 (every other, "duplicate" scope: a
    local-only branch checkout against the now-present clone) starts a
    single log line for it. Each scope, unique or duplicate, logs exactly one
    DEBUG "Created local branch '<name>', pointing to: <hash>" line when its
    local branch is first created — including the ``shards`` unique scopes,
    right after their own clone. So phase 2 cannot log its first such line
    until all ``shards`` phase-1 branch-creations are already logged: sorted
    ascending, the ``shards``-th "Created local branch" timestamp is exactly
    the phase-1/phase-2 boundary, no path/log-correlation guesswork needed.
    """
    # A few seconds of slack before the recorded start: the test's wall clock
    # (host) and the container's clock can be a touch skewed, and we'd rather
    # over-include a couple of harmless earlier lines than clip the real
    # "Preloading repo clones for scopes" marker.
    since_dt = datetime.fromtimestamp(since_epoch, tz=timezone.utc) - timedelta(
        seconds=5
    )
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out = compose(
        "logs", "--no-log-prefix", "--since", since_iso, "opal_server"
    ).stdout

    # First pass: find the CURRENT boot's start marker. The 5s --since slack
    # (and, in principle, docker's own log buffering) can let a stray tail
    # line from the container --force-recreate just killed leak in; taking
    # the LAST "Preloading" occurrence (it logs once per boot) rather than
    # the first correctly lands on this boot's, not a leaked prior one's.
    events = []  # (ts, kind) for every recognized marker line, unfiltered
    sync_start_ts = None
    for line in out.splitlines():
        ts = _parse_log_line_ts(line)
        if ts is None:
            continue
        clean = _ANSI_RE.sub("", line)
        if "Preloading repo clones for scopes" in clean:
            sync_start_ts = ts if sync_start_ts is None else max(sync_start_ts, ts)
            events.append((ts, "sync_start"))
        elif "Cloning repo at" in clean:
            events.append((ts, "clone_start"))
        elif "Clone completed:" in clean:
            events.append((ts, "clone_done"))
        elif "Created local branch '" in clean:
            events.append((ts, "branch_created"))

    # Second pass: discard anything at/before this boot's own start marker —
    # strictly-after drops leaked prior-boot lines without needing them to be
    # individually distinguishable from this boot's real events.
    clone_start_ts, clone_done_ts, branch_created_ts = [], [], []
    if sync_start_ts is not None:
        for ts, kind in events:
            if ts <= sync_start_ts:
                continue
            if kind == "clone_start":
                clone_start_ts.append(ts)
            elif kind == "clone_done":
                clone_done_ts.append(ts)
            elif kind == "branch_created":
                branch_created_ts.append(ts)

    branch_created_ts.sort()
    result = {
        "sync_start_ts": sync_start_ts,
        "clone_events": len(clone_done_ts),
        "branch_created_events": len(branch_created_ts),
        # the network-only block: first clone dispatched -> last clone landed.
        "clone_block_s": None,
        # phase-1 total: process boot -> the shards-th local branch created
        # (the point at which every unique/phase-1 scope, clone + its own
        # local branch checkout, is done).
        "phase1_total_s": None,
        # phase-2 total: that boundary -> the last (k-th) local branch created.
        "phase2_total_s": None,
    }
    if clone_start_ts and clone_done_ts:
        result["clone_block_s"] = (
            max(clone_done_ts) - min(clone_start_ts)
        ).total_seconds()
    if sync_start_ts is not None and len(branch_created_ts) >= shards and shards > 0:
        boundary_ts = branch_created_ts[shards - 1]
        result["phase1_total_s"] = (boundary_ts - sync_start_ts).total_seconds()
        if len(branch_created_ts) >= k:
            result["phase2_total_s"] = (
                branch_created_ts[k - 1] - boundary_ts
            ).total_seconds()
    return result


@pytest.mark.skipif(
    not RUN_DEMO, reason="set RUN_SHARDS_DEMO=1 to run the SHARDS sweep demo"
)
@pytest.mark.timeout(2400)
# Same exemption test_boot.py carries: the mid-test --force-recreate resets
# container-local /proc PIDs, spanning two container generations across the
# fixture's before/after pid comparison.
@pytest.mark.allow_worker_restart
def test_boot_sharding_demo(opal):
    """Measure boot->all-served for K scopes on ONE shared repo, many branches.

    Reports whatever OPAL_TEST_SHARDS the compose stack was actually
    started with — this test does not itself vary SHARDS; the sweep driver
    (see module docstring) sets it per host-side invocation.
    """
    k = int(os.environ.get("MAIN_REPO_BRANCHES", "200"))
    shards = int(os.environ.get("OPAL_TEST_SHARDS", "1"))
    repo_url = gitea_repo_url("shared-policy")

    scope_ids = [f"shard-demo-{i}" for i in range(k)]
    for i, scope_id in enumerate(scope_ids):
        opal.put_scope(scope_id, repo_url, branch=f"branch-{i:04d}")

    # Start the clock at the recreate (same rationale as test_boot.py):
    # preload_scopes runs pre-fork, before /healthcheck answers, so starting
    # later would undercount it. --force-recreate wipes the container FS so
    # every scope is a cold clone/checkout, a deterministic fresh-boot
    # measurement. --no-deps leaves gitea/redis/postgres untouched.
    start = time.time()
    compose("up", "-d", "--no-deps", "--force-recreate", "opal_server")
    opal.wait_healthy(timeout=600)

    served = set()
    poll_deadline = time.time() + 1800
    while time.time() < poll_deadline:
        for scope_id in scope_ids:
            if scope_id in served:
                continue
            try:
                if opal.get_scope_policy(scope_id).status_code == 200:
                    served.add(scope_id)
            except requests.RequestException:
                pass
        if len(served) == k:
            break
        time.sleep(2)
    elapsed = time.time() - start

    # Phase-1 (clone) vs phase-2 (local branch checkout) breakdown, parsed
    # from this boot's own server logs (see _log_breakdown's docstring for
    # the boundary rationale). wait_healthy() already blocks until preload's
    # sync_scopes (both phases) has fully finished — pre-fork, before
    # /healthcheck answers — so by the time this test's own GET-polling loop
    # above starts, every scope's local branch already exists; the polling
    # loop's own K sequential HTTP round-trips (each triggering that scope's
    # FIRST make_bundle) are pure additive overhead on top of phase1+phase2,
    # not something SHARDS affects. `poll_overhead_s` below isolates that.
    breakdown = _log_breakdown(shards, k, since_epoch=start)
    phase1 = breakdown["phase1_total_s"]
    phase2 = breakdown["phase2_total_s"]
    clone_block = breakdown["clone_block_s"]
    poll_overhead = (
        elapsed - (phase1 + phase2) if phase1 is not None and phase2 is not None else None
    )
    per_branch_ms = (
        (phase2 / max(1, k - shards)) * 1000 if phase2 is not None and k > shards else None
    )

    print(
        f"SHARDS={shards} branches={k} boot_served={len(served)}/{k} "
        f"elapsed={elapsed:.1f}s "
        f"phase1_total={_fmt(phase1)}s clone_block={_fmt(clone_block)}s "
        f"phase2_total={_fmt(phase2)}s phase2_per_branch={_fmt(per_branch_ms)}ms "
        f"poll_overhead={_fmt(poll_overhead)}s "
        f"clone_events={breakdown['clone_events']}/{shards} "
        f"branch_created_events={breakdown['branch_created_events']}/{k}"
    )
    assert len(served) == k, f"only {len(served)}/{k} scopes served after boot"
