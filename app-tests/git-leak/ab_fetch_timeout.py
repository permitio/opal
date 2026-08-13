"""Standalone driver for the fetch-timeout A/B (PER-15158 PR4 telemetry
validation). NOT a pytest test (filename doesn't match test_*.py, so it is
never collected by the bed's normal `pytest` run) — run directly:

    cd app-tests/git-leak
    <venv>/bin/python ab_fetch_timeout.py

Validates the prod telemetry finding: prod's ~20-min boot is dominated by a
slow tail of hung/unreachable customer repos (each blocking up to the OS
network timeout because the deployed image has no effective per-fetch
timeout), not by the thousands of fast healthy scopes. PR3's
OPAL_SCOPES_GIT_FETCH_TIMEOUT bounds that tail. This sweeps the timeout on
ONE image (this repo's PR3 build) — no second image needed, since the
timeout is a runtime config knob, not a code difference.

Fleet per run: N_HEALTHY distinct local-Gitea repos + M_HUNG scopes pointed
at the `blackhole` sidecar (accepts the TCP handshake, never answers — see
docker-compose.yml and helpers.make_repo_unreachable). Mirrors prod's
healthy-majority + hung-tail shape, scaled down.

For each OPAL_SCOPES_GIT_FETCH_TIMEOUT value: force-recreate opal_server
(fresh container FS -> cold clone of every scope, the real fresh-boot
preload path used by ScopesPolicyWatcherTask.preload_scopes(), see
test_boot.py), then measure:
  1. boot -> all-N_HEALTHY-served (poll GET /scopes/{id}/policy)
  2. preload sweep duration, parsed from `docker compose logs opal_server`:
     first "Preloading repo clones for scopes" to the last terminal git-op
     event ("Clone completed:" / "Could not clone repo at" / "Timed out
     fetching") — i.e. wall time of ScopesService.sync_scopes() during
     preload, which is what scales with the timeout (the hung tail).
  3. hung-scope skip count (timeout+skip logged) and container restart
     count (crash/readiness-restart guard).

Writes results incrementally to REPORT_PATH after each timeout so a partial
run still leaves usable data.
"""
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests
from helpers import (
    OpalServerClient,
    compose,
    gitea_repo_url,
    list_seeded_repos,
    make_repo_unreachable,
)

REPORT_PATH = Path(
    "/Users/zivxx/github/opal/.superpowers/sdd/timeout-ab-report.md"
)

# Guard against a second concurrent invocation stepping on this run: both
# drive the SAME shared docker-compose project (container name conflicts /
# "removal already in progress") and the SAME REPORT_PATH (a second
# REPORT_PATH.write_text() truncates the first run's in-progress report).
# Seen in practice during development of this script. Refuse to start if a
# live lock is already held.
_LOCK_PATH = Path("/tmp/opal_ab_fetch_timeout.lock")

N_HEALTHY = 50
M_HUNG = 25
TIMEOUTS = [int(x) for x in os.environ.get("AB_TIMEOUTS", "120,30,15").split(",")]
MAX_WORKERS = int(os.environ.get("OPAL_TEST_GIT_MAX_WORKERS", "10"))

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TS_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f%z")


def _parse_ts(line: str):
    clean = _ANSI_RE.sub("", line)
    ts_str = clean.split("|", 1)[0].strip()
    for fmt in _TS_FORMATS:
        try:
            ts = datetime.strptime(ts_str, fmt)
            if ts.tzinfo is not None:
                ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
            return ts
        except ValueError:
            continue
    return None


def _log_metrics(since_epoch: float, hung_urls: set) -> dict:
    """Parse `docker compose logs opal_server` into the PRE-FORK preload-sweep
    window and per-event counts, mirroring test_boot_sharding_demo.py's
    _log_breakdown marker-parsing approach.

    IMPORTANT: gunicorn's `when_ready` hook (see scripts/gunicorn_conf.py)
    runs `preload_scopes()` -> `sync_scopes()` SYNCHRONOUSLY in the master,
    BEFORE any worker is forked/booted (confirmed empirically: no worker
    "Booting worker with pid" line, and no HTTP response, appears before the
    "Finished pre loading scopes..." line). Once the worker DOES boot, the
    app's own startup wiring immediately fires a SECOND, independent
    "OPAL Scopes: syncing N scopes" pass over the exact same scopes
    (confirmed by a repro: a "Timed out fetching" / re-fetch pass follows
    "Finished pre loading scopes..." within ~1s). That second pass is a
    RUNTIME resync, not part of the boot sweep -- if not excluded it
    contaminates (usually inflates) the measured sweep_s.

    We therefore bound every counted event to the half-open window
    (last "Preloading repo clones for scopes" occurrence this boot,
    first "Finished pre loading scopes..." occurrence after it]. No
    `--since` flag is used (--force-recreate always yields a brand new
    container, so `docker compose logs opal_server` only ever contains
    THIS boot's history anyway); using the full log and picking the LAST
    "Preloading" line as the anchor mirrors the SHARDS demo's own
    leaked-prior-line defense, so this is robust even if that assumption
    is ever violated.
    """
    out = compose("logs", "--no-log-prefix", "opal_server").stdout

    events = []
    for line in out.splitlines():
        ts = _parse_ts(line)
        if ts is None:
            continue
        clean = _ANSI_RE.sub("", line)
        if "Preloading repo clones for scopes" in clean:
            events.append((ts, "sync_start"))
        elif "Finished pre loading scopes" in clean:
            events.append((ts, "sync_end"))
        elif "Cloning repo at" in clean:
            events.append((ts, "clone_start"))
        elif "Clone completed:" in clean:
            events.append((ts, "clone_done"))
        elif "Could not clone repo at" in clean:
            events.append((ts, "clone_timeout"))
        elif "Timed out fetching" in clean:
            events.append((ts, "fetch_timeout"))

    starts = sorted(ts for ts, k in events if k == "sync_start")
    sync_start_ts = starts[-1] if starts else None

    ends = sorted(
        ts
        for ts, k in events
        if k == "sync_end" and sync_start_ts is not None and ts > sync_start_ts
    )
    sync_end_ts = ends[0] if ends else None

    # the pre-fork window: strictly after sync_start, at/before sync_end (or
    # unbounded above if sync_end never showed up e.g. a hung boot).
    window = [
        (ts, k)
        for ts, k in events
        if sync_start_ts is not None
        and ts > sync_start_ts
        and (sync_end_ts is None or ts <= sync_end_ts)
    ]
    clone_done = [ts for ts, k in window if k == "clone_done"]
    clone_timeout = [ts for ts, k in window if k == "clone_timeout"]
    fetch_timeout = [ts for ts, k in window if k == "fetch_timeout"]
    terminal = clone_done + clone_timeout + fetch_timeout

    # tight sweep: sync_start -> the last terminal git-op event inside the
    # window (excludes the fixed ~SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT tail that
    # "Finished pre loading" additionally waits out).
    sweep_end_ts = max(terminal) if terminal else None
    sweep_s = (
        (sweep_end_ts - sync_start_ts).total_seconds()
        if sync_start_ts and sweep_end_ts
        else None
    )
    # marker-to-marker: sync_start -> "Finished pre loading scopes..." (what
    # actually gates worker boot / HTTP readiness); includes the fixed drain
    # overhead, constant across every timeout value in this sweep.
    preload_marker_s = (
        (sync_end_ts - sync_start_ts).total_seconds()
        if sync_start_ts and sync_end_ts
        else None
    )

    return {
        "sync_start_ts": sync_start_ts,
        "sync_end_ts": sync_end_ts,
        "sweep_end_ts": sweep_end_ts,
        "sweep_s": sweep_s,
        "preload_marker_s": preload_marker_s,
        "clone_completed": len(clone_done),
        "clone_timed_out": len(clone_timeout),
        "fetch_timed_out": len(fetch_timeout),
        "raw_log": out,
    }


def _recreate_opal_server(attempts: int = 4) -> None:
    """Stop+remove then recreate opal_server, tolerating a transient docker
    daemon race ("removal of container ... already in progress" / a stale
    temp container id from `--force-recreate`) with a short backoff retry.
    """
    last_exc = None
    for i in range(attempts):
        try:
            compose("rm", "-sf", "opal_server")
            compose("up", "-d", "--no-deps", "opal_server")
            return
        except RuntimeError as exc:
            last_exc = exc
            print(f"[ab] recreate attempt {i + 1}/{attempts} failed: {exc}")
            time.sleep(5)
    raise RuntimeError(
        f"opal_server recreate failed after {attempts} attempts: {last_exc}"
    )


def _container_restart_count(service: str = "opal_server") -> int:
    cid = compose("ps", "-q", service).stdout.strip()
    if not cid:
        return -1
    import subprocess

    out = subprocess.run(
        ["docker", "inspect", "-f", "{{.RestartCount}}", cid],
        capture_output=True,
        text=True,
    ).stdout.strip()
    try:
        return int(out)
    except ValueError:
        return -1


def _container_status(service: str = "opal_server") -> str:
    cid = compose("ps", "-q", service).stdout.strip()
    if not cid:
        return "missing"
    import subprocess

    out = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Status}}", cid],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return out


def _append_report(text: str) -> None:
    with open(REPORT_PATH, "a") as f:
        f.write(text)


def _acquire_lock() -> None:
    if _LOCK_PATH.exists():
        try:
            held_by = _LOCK_PATH.read_text().strip()
        except OSError:
            held_by = "?"
        raise RuntimeError(
            f"{_LOCK_PATH} already held (pid {held_by}) -- another "
            f"ab_fetch_timeout.py run appears to be in progress against the "
            f"same docker-compose project/report path. Refusing to start "
            f"concurrently."
        )
    _LOCK_PATH.write_text(str(os.getpid()))


def _release_lock() -> None:
    try:
        if _LOCK_PATH.exists() and _LOCK_PATH.read_text().strip() == str(os.getpid()):
            _LOCK_PATH.unlink()
    except OSError:
        pass


def main():
    _acquire_lock()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        "# Fetch-timeout A/B (PER-15158 PR4) - LOCAL git-leak bed\n\n"
        f"Started: {datetime.now(timezone.utc).isoformat()}\n\n"
        "STRICTLY LOCAL: local Gitea (healthy repos) + local `blackhole` "
        "socat sidecar (hung repos) + opal_server built from this repo's "
        "source (docker/Dockerfile, target=server). No prod/staging/"
        "external host touched.\n\n"
        f"Fleet per run: N_HEALTHY={N_HEALTHY} distinct local-Gitea repos + "
        f"M_HUNG={M_HUNG} scopes pointed at the `blackhole` sidecar. "
        f"OPAL_SCOPES_GIT_MAX_WORKERS={MAX_WORKERS} (bed default).\n\n"
        "One opal_server image (this repo's PR3 build); "
        "OPAL_SCOPES_GIT_FETCH_TIMEOUT is swept as a runtime config knob "
        f"across {TIMEOUTS}.\n\n"
    )

    os.environ["REPO_COUNT"] = str(N_HEALTHY)
    print(f"[ab] bringing up stack (REPO_COUNT={N_HEALTHY}) ...")
    compose("up", "-d", "--build")
    compose("wait", "seed")

    opal = OpalServerClient()
    opal.wait_healthy(timeout=180)

    healthy_repos = list_seeded_repos(N_HEALTHY)
    healthy_scope_ids = [f"ab-healthy-{i}" for i in range(N_HEALTHY)]
    hung_scope_ids = [f"ab-hung-{i}" for i in range(M_HUNG)]
    hung_urls = set()

    print(f"[ab] registering {N_HEALTHY} healthy + {M_HUNG} hung scopes ...")
    for scope_id, repo in zip(healthy_scope_ids, healthy_repos):
        opal.put_scope(scope_id, gitea_repo_url(repo))
    for i, scope_id in enumerate(hung_scope_ids):
        url = make_repo_unreachable(f"ab-dead-{i}")
        hung_urls.add(url)
        opal.put_scope(scope_id, url, branch="main")

    results = []
    for timeout in TIMEOUTS:
        print(f"\n[ab] === OPAL_SCOPES_GIT_FETCH_TIMEOUT={timeout} ===")
        os.environ["OPAL_TEST_GIT_FETCH_TIMEOUT"] = str(timeout)

        # worst-case bound: ceil(M_HUNG / MAX_WORKERS) waves of `timeout`,
        # plus generous margin for the healthy cascade + container boot.
        waves = -(-M_HUNG // MAX_WORKERS)
        served_budget = waves * timeout + 180
        healthcheck_budget = waves * timeout + 300

        start = time.time()
        # robust recreate: `--force-recreate` intermittently races on a stale
        # temp container id ("No such container: <hex>_...") or hits "removal
        # already in progress"; stop+rm then up, with a retry.
        _recreate_opal_server()
        try:
            opal.wait_healthy(timeout=healthcheck_budget)
            recreate_ok = True
        except RuntimeError as exc:
            print(f"[ab] WARNING: wait_healthy did not return: {exc}")
            recreate_ok = False

        served = set()
        poll_deadline = time.time() + served_budget
        last_status = {}
        while time.time() < poll_deadline:
            for scope_id in healthy_scope_ids:
                if scope_id in served:
                    continue
                try:
                    resp = opal.get_scope_policy(scope_id)
                    last_status[scope_id] = resp.status_code
                    if resp.status_code == 200:
                        served.add(scope_id)
                except requests.RequestException as exc:
                    last_status[scope_id] = repr(exc)
            if len(served) == N_HEALTHY:
                break
            time.sleep(2)
        healthy_served_s = time.time() - start

        metrics = _log_metrics(since_epoch=start, hung_urls=hung_urls)
        restart_count = _container_restart_count()
        status = _container_status()

        row = {
            "timeout": timeout,
            "healthy_served": len(served),
            "healthy_served_s": healthy_served_s,
            "all_healthy_served": len(served) == N_HEALTHY,
            "sweep_s": metrics["sweep_s"],
            "preload_marker_s": metrics["preload_marker_s"],
            "clone_completed": metrics["clone_completed"],
            "clone_timed_out": metrics["clone_timed_out"],
            "fetch_timed_out": metrics["fetch_timed_out"],
            "hung_skipped": metrics["clone_timed_out"] + metrics["fetch_timed_out"],
            "container_restart_count": restart_count,
            "container_status": status,
            "recreate_ok": recreate_ok,
        }
        results.append(row)

        print(
            f"[ab] timeout={timeout}s healthy_served={row['healthy_served']}/"
            f"{N_HEALTHY} in {healthy_served_s:.1f}s, sweep={metrics['sweep_s']}, "
            f"preload_marker={metrics['preload_marker_s']}, "
            f"hung_skipped={row['hung_skipped']}/{M_HUNG}, "
            f"restart_count={restart_count}, status={status}"
        )
        if len(served) != N_HEALTHY:
            missing = [s for s in healthy_scope_ids if s not in served]
            print(f"[ab] WARNING: missing healthy scopes: {missing[:5]}... "
                  f"last_status sample: "
                  f"{ {k: last_status.get(k) for k in missing[:5]} }")

        _append_report(
            f"## timeout={timeout}s\n\n"
            f"- healthy served: {row['healthy_served']}/{N_HEALTHY} "
            f"in {healthy_served_s:.1f}s "
            f"(all_served={row['all_healthy_served']})\n"
            f"- preload sweep duration (sync_start -> last terminal git-op "
            f"event, parsed from server log): {metrics['sweep_s']}\n"
            f"- preload marker duration (sync_start -> 'Finished pre loading "
            f"scopes...', includes the fixed SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT "
            f"tail): {metrics['preload_marker_s']}\n"
            f"- hung scopes (pre-fork window only): "
            f"clone_timed_out={metrics['clone_timed_out']}, "
            f"fetch_timed_out={metrics['fetch_timed_out']} "
            f"(total skipped {row['hung_skipped']}/{M_HUNG})\n"
            f"- healthy clones completed (log): {metrics['clone_completed']}\n"
            f"- container restart_count={restart_count}, status={status}\n\n"
        )

        # Log excerpt for the timeout+skip lines, capped for readability.
        skip_lines = [
            l
            for l in metrics["raw_log"].splitlines()
            if "Could not clone repo at" in l or "Timed out fetching" in l
        ]
        _append_report(
            "<details><summary>sample timeout/skip log lines, RAW/unwindowed "
            f"-- may include the post-boot runtime resync pass too "
            f"({len(skip_lines)} total)</summary>\n\n```\n"
            + "\n".join(skip_lines[:8])
            + "\n```\n</details>\n\n"
        )

    # ---- summary table ----
    lines = [
        "\n## Summary\n\n",
        "| timeout (s) | healthy-served (s) | preload-sweep (s) | preload-marker (s) | hung skipped | container restarts |\n",
        "|---:|---:|---:|---:|---:|---:|\n",
    ]
    def _f(v):
        return f"{v:.1f}" if isinstance(v, (int, float)) else "NA"

    for r in results:
        lines.append(
            f"| {r['timeout']} | {r['healthy_served_s']:.1f} "
            f"({r['healthy_served']}/{N_HEALTHY}) | "
            f"{_f(r['sweep_s'])} | {_f(r['preload_marker_s'])} | "
            f"{r['hung_skipped']}/{M_HUNG} | "
            f"{r['container_restart_count']} |\n"
        )
    _append_report("".join(lines))

    print("\n[ab] SUMMARY")
    for r in results:
        print(
            f"  timeout={r['timeout']:>4}s  healthy_served={r['healthy_served_s']:.1f}s "
            f"({r['healthy_served']}/{N_HEALTHY})  sweep={r['sweep_s']}  "
            f"hung_skipped={r['hung_skipped']}/{M_HUNG}  "
            f"restarts={r['container_restart_count']}"
        )

    print(f"\n[ab] report: {REPORT_PATH}")
    return results


if __name__ == "__main__":
    try:
        main()
    finally:
        _release_lock()
