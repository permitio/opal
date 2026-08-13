"""Head-to-head boot comparison: OLD (pre-PR3) vs NEW (PR3) opal_server image,
same fleet, LOCAL git-leak bed. NOT a pytest test (filename != test_*.py).

    cd app-tests/git-leak
    <venv>/bin/python head_to_head.py

Companion to ab_fetch_timeout.py. The A/B swept the fetch-timeout knob on ONE
(PR3) image. This instead compares TWO IMAGES built from source:

  * old = 76f898ec (parent of the first PR3 commit): serial `sync_scopes`
    (`for scope in scopes: await sync_scope(...)`, one hung repo blocks every
    repo behind it head-of-line) AND no SCOPES_GIT_FETCH_TIMEOUT config at all
    (added later by 245f80ba) -- the behaviour deployed in prod today.
  * new = current tree (PR3): bounded-concurrency two-phase sync_scopes +
    per-fetch timeout.

Both images preload identically -- gunicorn `when_ready` runs
ScopesPolicyWatcherTask.preload_scopes() -> sync_scopes() SYNCHRONOUSLY in the
master before any worker forks (see scripts/gunicorn_conf.py, unchanged across
the range). So the whole preload sweep must finish before ANY worker boots and
ANY scope serves: time-to-serve-all-healthy == full boot preload sweep, a
directly comparable number between the two images.

Fair, prod-faithful hung model: the `slowfail` sidecar (hh-override.yml)
accepts the TCP handshake, sleeps HANG_SECONDS, then CLOSES -> the git clone
fails after ~HANG_SECONDS on BOTH images (image-independent, mirrors prod's
finite ~30-212s broken-repo tail). This lets both images complete, unlike
`blackhole` (1h hang) which would wedge the old image indefinitely.

Configs (same 30 healthy + 12 hung fleet each):
  old      -- serial, no timeout            -> ~M_HUNG x HANG serial
  new@120  -- PR3, prod-default timeout      -> concurrency alone
  new@15   -- PR3, tuned low timeout         -> concurrency + tight bound

Metric per config: time-to-serve all N_HEALTHY (poll GET /scopes/{id}/policy),
whether boot completed within the cap, best-effort preload-sweep from the
server log, container restart count.
"""
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests
from helpers import OpalServerClient, gitea_repo_url, list_seeded_repos

_HERE = Path(__file__).resolve().parent
REPORT_PATH = Path("/Users/zivxx/github/opal/.superpowers/sdd/head-to-head-report.md")
_LOCK_PATH = Path("/tmp/opal_hh.lock")

N_HEALTHY = 30
M_HUNG = 12
MAX_WORKERS = int(os.environ.get("HH_MAX_WORKERS", "10"))
HANG_SECONDS = int(os.environ.get("HH_HANG_SECONDS", "25"))
SLOWFAIL_HOST = "slowfail"
GITEA_USER = "opaladmin"

# (label, image tag, OPAL fetch timeout or None). old ignores the timeout env
# entirely (no such config at 76f898ec); we still pass a value so the compose
# var is defined -- it is simply inert there.
CONFIGS = [
    ("old", "opal-server:old", None),
    ("new@120", "opal-server:new", 120),
    ("new@15", "opal-server:new", 15),
]

# generous per-config poll cap: old is serial (~M_HUNG x HANG); give big margin.
POLL_CAP = {"old": 900, "new@120": 400, "new@15": 400}

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TS_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f%z")


def hh_compose(*args, timeout: int = 1200) -> subprocess.CompletedProcess:
    """`docker compose -f docker-compose.yml -f hh-override.yml <args>` in the
    bed dir. Surfaces captured output on failure. HH_IMAGE / HH_HANG_SECONDS /
    OPAL_TEST_* are read from the environment by compose variable-substitution.
    """
    proc = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml", "-f", "hh-override.yml", *args],
        cwd=_HERE,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"`docker compose {' '.join(args)}` failed ({proc.returncode})\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc


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


def _log_metrics() -> dict:
    """Best-effort preload-sweep parse from the fresh container's log. Same
    marker approach as ab_fetch_timeout.py. Markers may differ on the OLD image
    -> fields fall back to None; the headline metric is the external
    healthy-served poll, which is image-independent.
    """
    out = hh_compose("logs", "--no-log-prefix", "opal_server").stdout
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
        elif "Clone completed:" in clean:
            events.append((ts, "clone_done"))
        elif "Could not clone repo at" in clean:
            events.append((ts, "clone_fail"))
        elif "Timed out fetching" in clean:
            events.append((ts, "fetch_timeout"))

    starts = sorted(ts for ts, k in events if k == "sync_start")
    sync_start_ts = starts[-1] if starts else None
    ends = sorted(
        ts for ts, k in events
        if k == "sync_end" and sync_start_ts is not None and ts > sync_start_ts
    )
    sync_end_ts = ends[0] if ends else None
    window = [
        (ts, k) for ts, k in events
        if sync_start_ts is not None and ts > sync_start_ts
        and (sync_end_ts is None or ts <= sync_end_ts)
    ]
    clone_done = [ts for ts, k in window if k == "clone_done"]
    clone_fail = [ts for ts, k in window if k == "clone_fail"]
    fetch_timeout = [ts for ts, k in window if k == "fetch_timeout"]
    terminal = clone_done + clone_fail + fetch_timeout
    sweep_end_ts = max(terminal) if terminal else None
    sweep_s = (
        (sweep_end_ts - sync_start_ts).total_seconds()
        if sync_start_ts and sweep_end_ts else None
    )
    marker_s = (
        (sync_end_ts - sync_start_ts).total_seconds()
        if sync_start_ts and sync_end_ts else None
    )
    return {
        "sweep_s": sweep_s,
        "marker_s": marker_s,
        "clone_done": len(clone_done),
        "clone_fail": len(clone_fail),
        "fetch_timeout": len(fetch_timeout),
        "raw_log": out,
    }


def _recreate_opal_server(attempts: int = 4) -> None:
    last_exc = None
    for i in range(attempts):
        try:
            hh_compose("rm", "-sf", "opal_server")
            hh_compose("up", "-d", "--no-deps", "--no-build", "opal_server")
            return
        except RuntimeError as exc:
            last_exc = exc
            print(f"[hh] recreate attempt {i + 1}/{attempts} failed: {exc}")
            time.sleep(5)
    raise RuntimeError(f"opal_server recreate failed after {attempts}: {last_exc}")


def _restart_count() -> int:
    cid = hh_compose("ps", "-q", "opal_server").stdout.strip()
    if not cid:
        return -1
    out = subprocess.run(
        ["docker", "inspect", "-f", "{{.RestartCount}}", cid],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return int(out)
    except ValueError:
        return -1


def _append(text: str) -> None:
    with open(REPORT_PATH, "a") as f:
        f.write(text)


def _acquire_lock() -> None:
    if _LOCK_PATH.exists():
        held = _LOCK_PATH.read_text().strip() if _LOCK_PATH.exists() else "?"
        raise RuntimeError(
            f"{_LOCK_PATH} already held (pid {held}); refusing concurrent run."
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
        "# Head-to-head: OLD (pre-PR3) vs NEW (PR3) opal_server image "
        "- LOCAL git-leak bed\n\n"
        f"Started: {datetime.now(timezone.utc).isoformat()}\n\n"
        "STRICTLY LOCAL: two images built from source (old=76f898ec, "
        "new=current tree), same fleet, local Gitea + `slowfail` socat sidecar "
        f"(finite ~{HANG_SECONDS}s image-independent hang). No prod/staging "
        "touched.\n\n"
        f"Fleet per config: {N_HEALTHY} healthy local-Gitea repos + {M_HUNG} "
        f"hung scopes (slowfail sidecar), interleaved. "
        f"OPAL_SCOPES_GIT_MAX_WORKERS={MAX_WORKERS}. Both images preload in the "
        "gunicorn master before fork, so time-to-serve-all-healthy == full boot "
        "preload sweep.\n\n"
        "| config | represents |\n|---|---|\n"
        "| old | deployed today: serial sync_scopes, no fetch timeout |\n"
        "| new@120 | deploy PR3, prod-default timeout (concurrency only) |\n"
        "| new@15 | deploy PR3 + tuned low timeout |\n\n"
    )

    # ---- bring up the stack once (build seed; opal_server uses new image) ----
    os.environ["REPO_COUNT"] = str(N_HEALTHY)
    os.environ["HH_HANG_SECONDS"] = str(HANG_SECONDS)
    os.environ["HH_IMAGE"] = "opal-server:new"
    os.environ["OPAL_TEST_GIT_MAX_WORKERS"] = str(MAX_WORKERS)
    print(f"[hh] bringing up stack (REPO_COUNT={N_HEALTHY}, HANG={HANG_SECONDS}s) ...")
    # --no-build for opal_server would also skip building `seed`; build only what
    # needs it, then rely on prebuilt opal_server image at recreate time.
    hh_compose("up", "-d", "--build")
    hh_compose("wait", "seed")

    opal = OpalServerClient()
    opal.wait_healthy(timeout=180)

    healthy_repos = list_seeded_repos(N_HEALTHY)
    healthy_ids = [f"hh-healthy-{i}" for i in range(N_HEALTHY)]
    hung_ids = [f"hh-hung-{i}" for i in range(M_HUNG)]

    # Interleave registration so hung repos are scattered among healthy ones
    # (prod-faithful): a hung repo early in the serial sweep blocks the healthy
    # repos behind it. Even if the scope store reorders, all M_HUNG are still
    # processed serially somewhere in the old sweep, so time-to-LAST-healthy
    # tracks the full sweep either way.
    print(f"[hh] registering {N_HEALTHY} healthy + {M_HUNG} hung (interleaved) ...")
    hung_every = max(1, N_HEALTHY // M_HUNG)
    hi = 0
    for idx, (scope_id, repo) in enumerate(zip(healthy_ids, healthy_repos)):
        opal.put_scope(scope_id, gitea_repo_url(repo))
        if idx % hung_every == 0 and hi < M_HUNG:
            url = f"http://{SLOWFAIL_HOST}/{GITEA_USER}/hh-dead-{hi}.git"
            opal.put_scope(hung_ids[hi], url, branch="main")
            hi += 1
    while hi < M_HUNG:  # any remaining hung
        url = f"http://{SLOWFAIL_HOST}/{GITEA_USER}/hh-dead-{hi}.git"
        opal.put_scope(hung_ids[hi], url, branch="main")
        hi += 1

    results = []
    for label, image, timeout in CONFIGS:
        print(f"\n[hh] === {label} (image={image}, timeout={timeout}) ===")
        os.environ["HH_IMAGE"] = image
        os.environ["OPAL_TEST_GIT_FETCH_TIMEOUT"] = str(timeout if timeout else 120)

        cap = POLL_CAP[label]
        start = time.time()
        _recreate_opal_server()
        try:
            opal.wait_healthy(timeout=cap)
            healthy_ok = True
        except RuntimeError as exc:
            print(f"[hh] WARNING: wait_healthy did not return within {cap}s: {exc}")
            healthy_ok = False

        served = set()
        deadline = time.time() + cap
        last_status = {}
        while time.time() < deadline:
            for scope_id in healthy_ids:
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
            time.sleep(3)
        served_s = time.time() - start
        completed = len(served) == N_HEALTHY

        metrics = _log_metrics()
        restarts = _restart_count()
        row = {
            "label": label, "image": image, "timeout": timeout,
            "served": len(served), "served_s": served_s, "completed": completed,
            "sweep_s": metrics["sweep_s"], "marker_s": metrics["marker_s"],
            "clone_done": metrics["clone_done"], "clone_fail": metrics["clone_fail"],
            "fetch_timeout": metrics["fetch_timeout"], "restarts": restarts,
        }
        results.append(row)
        print(
            f"[hh] {label}: served={len(served)}/{N_HEALTHY} in {served_s:.1f}s "
            f"completed={completed} sweep={metrics['sweep_s']} "
            f"clone_fail={metrics['clone_fail']} fetch_timeout={metrics['fetch_timeout']} "
            f"restarts={restarts}"
        )
        if not completed:
            missing = [s for s in healthy_ids if s not in served]
            print(f"[hh] WARNING: {len(missing)} healthy NOT served; sample "
                  f"{ {k: last_status.get(k) for k in missing[:5]} }")

        _append(
            f"## {label} (image={image}, OPAL_SCOPES_GIT_FETCH_TIMEOUT={timeout})\n\n"
            f"- healthy served: {len(served)}/{N_HEALTHY} in {served_s:.1f}s "
            f"(completed={completed})\n"
            f"- preload sweep (log, best-effort): {metrics['sweep_s']}\n"
            f"- preload marker (log, best-effort): {metrics['marker_s']}\n"
            f"- clones completed / clone-fail / fetch-timeout (log): "
            f"{metrics['clone_done']} / {metrics['clone_fail']} / {metrics['fetch_timeout']}\n"
            f"- container restarts: {restarts}\n\n"
        )

    # ---- summary ----
    lines = [
        "\n## Summary\n\n",
        "| config | image | timeout | healthy-served (s) | completed | preload-sweep (s) | restarts |\n",
        "|---|---|---:|---:|:--:|---:|---:|\n",
    ]

    def _f(v):
        return f"{v:.1f}" if isinstance(v, (int, float)) else "NA"

    for r in results:
        lines.append(
            f"| {r['label']} | {r['image']} | {r['timeout']} | "
            f"{r['served_s']:.1f} ({r['served']}/{N_HEALTHY}) | "
            f"{'yes' if r['completed'] else 'NO'} | {_f(r['sweep_s'])} | "
            f"{r['restarts']} |\n"
        )
    _append("".join(lines))

    print("\n[hh] SUMMARY")
    for r in results:
        print(
            f"  {r['label']:>8}: {r['served_s']:.1f}s "
            f"({r['served']}/{N_HEALTHY}) completed={r['completed']} "
            f"sweep={r['sweep_s']}"
        )
    print(f"\n[hh] report: {REPORT_PATH}")
    return results


if __name__ == "__main__":
    try:
        main()
    finally:
        _release_lock()
