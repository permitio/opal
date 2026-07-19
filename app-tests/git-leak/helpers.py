"""HTTP + infra helpers for the git-leak test bed."""
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

OPAL_URL = "http://localhost:7002"
# reachable from inside the opal_server container (compose network)
GITEA_INTERNAL_URL = "http://gitea:3000"
# reachable from the host-side test harness (published port, see docker-compose.yml)
GITEA_HOST_URL = "http://localhost:13000"
GITEA_USER = "opaladmin"
GITEA_PASSWORD = "opaladmin"

# the `blackhole` compose service (alpine/socat) accepts the TCP handshake then
# never answers, so a clone connects and blocks reading the response — a
# deterministic hang. Reachable from the opal_server container on the compose
# network. (A TEST-NET-1 address was rejected too fast on many networks, so the
# clone failed fast instead of hanging and the offline scenario wasn't exercised.)
UNREACHABLE_HOST = "blackhole"

# the compose project lives next to this file; compose() runs from here
_COMPOSE_DIR = str(Path(__file__).resolve().parent)


class OpalServerClient:
    def __init__(self, base_url: str = OPAL_URL):
        self.base_url = base_url.rstrip("/")
        # scope_ids created via put_scope, so a per-test fixture can delete them
        # on teardown. Clone paths are keyed by repo URL (not scope_id), so a
        # scope left behind by one test shares a GitPolicyFetcher cache entry
        # with any other test pointing at the same seeded repo — without cleanup
        # that leftover keeps the entry alive and pollutes a drain assertion.
        self._created_scopes: set = set()

    def wait_healthy(self, timeout: int = 180) -> None:
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                if (
                    requests.get(f"{self.base_url}/healthcheck", timeout=5).status_code
                    == 200
                ):
                    return
            except requests.RequestException as exc:
                last = exc
            time.sleep(2)
        raise RuntimeError(f"opal-server not healthy in {timeout}s (last: {last})")

    def stats(self, samples: int = 3, interval: float = 0.1) -> Dict[str, Any]:
        """Read the git-fetcher cache stats, merged across a few reads.

        The stack runs a single uvicorn worker (see docker-compose.yml), so the
        per-process ``GitPolicyFetcher`` caches are read deterministically — a
        read can't miss the worker that fetched. Sampling a few times and taking
        the ``max`` per key only smooths over a read that races an in-flight
        mutation; it is not relied on to paper over multi-worker nondeterminism
        (which the single-worker setup removes outright).

        Merge semantics: numeric counts take the max across samples (peak
        smoothing); ``pid`` and the ``*_keys`` lists are last-wins. The
        count fields and their paired ``*_keys`` lists are therefore only
        guaranteed mutually consistent at ``samples=1`` — which is what
        every consistency-sensitive consumer (the invariant checker,
        per-pid sampling) uses. Do not assert
        ``len(stats["repos_keys"]) == stats["repos"]`` on a multi-sample
        merge.
        """
        merged: Dict[str, Any] = {}
        for i in range(max(1, samples)):
            resp = requests.get(
                f"{self.base_url}/internal/git-fetcher-cache-stats", timeout=10
            )
            resp.raise_for_status()
            for key, value in resp.json().items():
                if key != "pid" and isinstance(value, (int, float)):
                    merged[key] = max(merged.get(key, 0), value)
                else:
                    # pid and the *_keys lists: last-wins (single-worker stack
                    # makes every read hit the same worker anyway)
                    merged[key] = value
            if i < samples - 1:
                time.sleep(interval)
        return merged

    def put_scope(self, scope_id: str, repo_url: str, branch: str = "main") -> None:
        body = {
            "scope_id": scope_id,
            "policy": {
                "source_type": "git",
                "url": repo_url,
                "auth": {"auth_type": "none"},
                "branch": branch,
                "directories": ["."],
                "extensions": [".rego", ".json"],
                "manifest": ".manifest",
                "poll_updates": False,
            },
            "data": {"entries": []},
        }
        # the scope router mounts at prefix="/scopes" with @router.put("")
        resp = requests.put(f"{self.base_url}/scopes", json=body, timeout=30)
        resp.raise_for_status()
        self._created_scopes.add(scope_id)

    def delete_scope(self, scope_id: str) -> None:
        resp = requests.delete(f"{self.base_url}/scopes/{scope_id}", timeout=30)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()
        self._created_scopes.discard(scope_id)

    def list_scope_ids(self) -> List[str]:
        """All scope ids the server currently knows (GET /scopes)."""
        resp = requests.get(f"{self.base_url}/scopes", timeout=30)
        resp.raise_for_status()
        return [s["scope_id"] for s in resp.json()]

    def hard_reset(self, timeout: int = 600) -> None:
        """Recover the server from a saturated fetch executor by wiping state.

        When a test leaves many clones hung (the offline-repo test saturates the
        executor on purpose), per-scope DELETEs would queue *behind* those hung
        threads, and a plain restart would have ``preload_scopes`` re-clone the
        offline scopes and saturate again. Instead: stop the server (killing the
        hung threads), flush the Redis scope store so nothing is re-cloned, then
        start clean. Used in that test's teardown so the session-scoped stack is
        usable by every later test.
        """
        compose("stop", "opal_server")
        try:
            compose("exec", "-T", "redis", "redis-cli", "FLUSHALL")
        finally:
            # Always bring the server back up, even if the flush failed: leaving
            # it stopped would fail every later session-scoped test, and since
            # this runs in a test's `finally` it would also mask the real result.
            compose("start", "opal_server")
            self._created_scopes.clear()
            self.wait_healthy(timeout=timeout)

    def delete_all_scopes(self, drain_timeout: int = 3) -> None:
        """Delete every scope the *server* knows (not just this client's), then
        best-effort wait for the caches to drain — a clean slate independent of
        what any prior, possibly-failed, test left behind.

        Best-effort drain by design: on master, delete never purges the caches
        (the leak this suite gates), so the wait can't succeed there — hence the
        short ``drain_timeout`` (this runs in *every* test's setup and teardown,
        so a long wait for a state that can't occur on master would be pure dead
        time per test). Post-PR2 the purge is near-instant, so a few seconds is
        ample. The DELETEs themselves are synchronous, so the scope store is
        already clean before this wait — the wait only smooths the in-process
        cache count. This runs in fixture setup/teardown, so a failure here must
        not mask the test, hence the broad excepts and bounded wait.
        """
        try:
            for scope_id in self.list_scope_ids():
                try:
                    self.delete_scope(scope_id)
                except Exception:
                    self._created_scopes.discard(scope_id)
        except Exception:
            pass
        self._created_scopes.clear()
        deadline = time.time() + drain_timeout
        while time.time() < deadline:
            try:
                # Single snapshot: we're waiting for zero, so the peak-merge
                # (max over samples) would only delay observing the drain.
                if self.stats(samples=1)["repo_locks"] == 0:
                    return
            except Exception:
                # A transient stats-read failure is not proof of a drain — keep
                # polling until the deadline rather than returning early, which
                # would let a not-yet-drained cache leak into the next test.
                pass
            time.sleep(1)

    def get_scope_policy(self, scope_id: str) -> requests.Response:
        """Fetch a scope's policy bundle (GET /scopes/{id}/policy).

        A 200 here proves the scope's repo was cloned and is being
        served — the signal that a healthy scope still works while
        another scope's clone is hanging.
        """
        return requests.get(f"{self.base_url}/scopes/{scope_id}/policy", timeout=30)

    def refresh_all(self) -> None:
        # POST /scopes/refresh publishes on the webhook topic so the leader
        # re-syncs all scopes. The second sync takes the discover/fetch path
        # (not the first-sync clone path), which is what populates the `repos`
        # and `repos_last_fetched` caches. A missing route is a real error and
        # is surfaced via raise_for_status.
        resp = requests.post(f"{self.base_url}/scopes/refresh", timeout=30)
        resp.raise_for_status()


class GiteaAdmin:
    """Host-side admin client for the test bed's Gitea.

    The ``seed`` sidecar does the bulk repo creation from inside the compose
    network; this class lets a test inspect or mutate Gitea repos directly
    from the host (e.g. assert seeding happened, or add/remove a single repo
    for a specific scenario). It authenticates with the admin user that the
    ``gitea-admin`` sidecar created, over the published host port.
    """

    def __init__(
        self,
        base_url: str = GITEA_HOST_URL,
        user: str = GITEA_USER,
        password: str = GITEA_PASSWORD,
    ):
        self.base_url = base_url.rstrip("/")
        self._user = user
        self._auth = (user, password)

    def repo_exists(self, name: str) -> bool:
        resp = requests.get(
            f"{self.base_url}/api/v1/repos/{self._user}/{name}",
            auth=self._auth,
            timeout=10,
        )
        return resp.status_code == 200

    def list_repos(self) -> List[str]:
        names: List[str] = []
        page = 1
        while True:
            resp = requests.get(
                f"{self.base_url}/api/v1/users/{self._user}/repos",
                params={"page": page, "limit": 50},
                auth=self._auth,
                timeout=10,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            names.extend(r["name"] for r in batch)
            page += 1
        return names

    def create_repo(self, name: str) -> None:
        if self.repo_exists(name):
            return
        resp = requests.post(
            f"{self.base_url}/api/v1/user/repos",
            json={
                "name": name,
                "private": False,
                "auto_init": True,
                "default_branch": "main",
            },
            auth=self._auth,
            timeout=10,
        )
        resp.raise_for_status()

    def delete_repo(self, name: str) -> None:
        resp = requests.delete(
            f"{self.base_url}/api/v1/repos/{self._user}/{name}",
            auth=self._auth,
            timeout=10,
        )
        if resp.status_code not in (204, 404):
            resp.raise_for_status()


class RepoMutator:
    """Host-side git mutations against a bed Gitea repo (force-push, branch
    ops) — the remote-transition tests' hands.

    Uses GitPython over the published host port with admin basic-auth.
    """

    def __init__(self, name: str, workdir: Path):
        import git as gitpython

        self._url = (
            f"http://{GITEA_USER}:{GITEA_PASSWORD}@localhost:13000/"
            f"{GITEA_USER}/{name}.git"
        )
        self._clone = gitpython.Repo.clone_from(self._url, str(workdir / name))
        with self._clone.config_writer() as cw:
            cw.set_value("user", "name", "bed-mutator")
            cw.set_value("user", "email", "bed@test.local")

    def force_push_rewrite(self, branch: str = "main") -> None:
        self._clone.git.checkout(branch)
        self._clone.git.commit("--amend", "--allow-empty", "-m", "rewritten history")
        self._clone.git.push("--force", "origin", branch)

    def push_new_branch(self, branch: str) -> None:
        self._clone.git.checkout("-b", branch)
        self._clone.git.commit("--allow-empty", "-m", f"seed {branch}")
        self._clone.git.push("origin", branch)

    def delete_remote_branch(self, branch: str) -> None:
        self._clone.git.push("origin", f":{branch}")


def gitea_repo_url(name: str) -> str:
    # url reachable from inside the opal_server container
    return f"{GITEA_INTERNAL_URL}/{GITEA_USER}/{name}.git"


def make_repo_unreachable(name: str) -> str:
    """Return a git URL for ``name`` pointing at the ``blackhole`` sidecar.

    Simulates an offline/unreachable policy repo: ``blackhole`` (alpine/socat)
    accepts the TCP handshake then never answers, so the clone connects and
    blocks reading the git smart-HTTP response — a deterministic hang that
    exercises the missing fetch timeout on the scopes path (the bug PR3 fixes).
    The URL keeps the same ``/{user}/{name}.git`` shape as a real Gitea repo so
    the scope looks ordinary apart from the unreachable host.
    """
    return f"http://{UNREACHABLE_HOST}/{GITEA_USER}/{name}.git"


def compose(*args: str, timeout: int = 1200) -> subprocess.CompletedProcess:
    """Run `docker compose <args>`; on failure, surface the captured output.

    `capture_output=True` keeps compose noise out of passing tests, but
    a raw CalledProcessError shows only the exit code — so on failure we
    re-raise with the captured stdout/stderr embedded, otherwise a
    broken build/seed/ restart is opaque to debug.

    ``timeout`` (default 1200s) bounds each call: ``@pytest.mark.timeout`` does
    not cover session-scoped *fixture setup*, so a wedged ``up``/``wait``/build
    would otherwise hang to the CI job limit. On expiry we raise a clear error
    (subprocess.run kills the process group) instead of blocking indefinitely.
    """
    try:
        proc = subprocess.run(
            ["docker", "compose", *args],
            cwd=_COMPOSE_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"`docker compose {' '.join(args)}` timed out after {timeout}s\n"
            f"--- stdout ---\n{exc.stdout or ''}\n--- stderr ---\n{exc.stderr or ''}"
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"`docker compose {' '.join(args)}` failed (exit {proc.returncode})\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc


def worker_pids(service: str = "opal_server") -> set:
    """Return the set of gunicorn *worker* PIDs running inside ``service``.

    The server runs ``gunicorn`` (master) + ``UvicornWorker`` children (see
    ``scripts/start.sh``). When a worker's broadcaster reader gives up on a
    backbone disconnect it triggers a graceful shutdown and gunicorn respawns
    the worker with a *new* PID; the reconnecting broadcaster (PER-15065 / #915)
    instead recovers the reader in place and the worker keeps its PID. Comparing
    this set across a transient bounce is how the broadcaster test tells an
    in-place reconnect apart from a worker respawn.

    Implemented over ``/proc`` (no ``ps`` in the slim image): every gunicorn
    process' ``cmdline`` contains "gunicorn", and the master is the lowest PID
    (it exists before it forks any worker), so the workers are the rest. The
    match is done **host-side in Python**, not with ``grep gunicorn`` in the
    container: the scanning command's own ``sh -c`` wrapper has "gunicorn" in
    its command line, so an in-container grep would count that wrapper as a
    third "worker". The dump command below contains neither "gunicorn" nor
    "grep", so it cannot match itself.
    """
    out = compose(
        "exec",
        "-T",
        service,
        "sh",
        "-c",
        # emit "<pid> <cmdline>" per process; tr -d strips the NUL arg
        # separators so the args concatenate into one searchable token.
        # `|| true`: a momentary read failure must not raise from compose().
        "for d in /proc/[0-9]*/; do p=${d#/proc/}; p=${p%/}; "
        'echo "$p $(cat "$d/cmdline" 2>/dev/null | tr -d "\\000")"; '
        "done || true",
    ).stdout
    pids = []
    for line in out.splitlines():
        pid_str, _, cmd = line.partition(" ")
        if pid_str.isdigit() and "gunicorn" in cmd:
            pids.append(int(pid_str))
    pids.sort()
    if len(pids) <= 1:
        return set()  # only the master (or nothing) observed: no workers
    return set(pids[1:])  # drop the master (lowest PID); the rest are workers


# The reconnecting broadcaster (PER-15065 / #915) logs this line every time its
# reader (re)connects to the backbone channel — once at boot, and once more on
# each reconnect after a backbone drop (pubsub_resilience.py `_reader_loop` ->
# `_ensure_connected`). Counting it across a Postgres bounce positively proves a
# disconnect+reconnect actually happened.
_BROADCASTER_CONNECT_LOG = "Broadcaster listener connected to channel"


def broadcaster_connect_count(service: str = "opal_server") -> int:
    """Count broadcaster reader (re)connect log lines for ``service``.

    The postgres-bounce test asserts this COUNT *increased* across the bounce so
    the gate positively confirms the backbone actually dropped and the reader
    reconnected — without this, a bounce that failed to break the reader (a
    future Postgres shutdown-signal change, connection pooling, etc.) would leave
    the worker PIDs unchanged and pass the gate vacuously. Paired with
    ``worker_pids()`` unchanged (which proves the recovery was *in place*, not a
    respawn), the two together pin down the PER-15065 property.
    """
    # --no-log-prefix strips the "service | " column so the marker matches cleanly.
    out = compose("logs", "--no-log-prefix", service).stdout
    return out.count(_BROADCASTER_CONNECT_LOG)


def bounce_postgres(down_seconds: int = 5, during=None) -> None:
    """Stop Postgres, optionally run ``during()`` while it is down, restart it.

    ``during`` lets a test act inside the outage window (e.g. publish a scope
    while the backbone is down). It runs right after the stop; the remainder of
    ``down_seconds`` is then slept so the outage lasts at least that long
    regardless of how long the callback took. Postgres is brought back even if
    the callback raises — otherwise one failed callback would leave the
    session-scoped stack without its broadcaster for every later test — and the
    callback's exception then propagates.
    """
    compose("stop", "postgres")
    stopped_at = time.time()
    try:
        if during is not None:
            during()
    finally:
        remaining = down_seconds - (time.time() - stopped_at)
        if remaining > 0:
            time.sleep(remaining)
        # `up -d --wait` blocks until Postgres passes its healthcheck again (plain
        # `compose start` has no --wait), so a recovery poll that follows isn't
        # racing an unready broadcaster. --no-recreate keeps the same container.
        compose("up", "-d", "--wait", "--no-recreate", "postgres")


def wait_until(predicate, timeout: float, interval: float = 2.0) -> bool:
    """Poll ``predicate()`` until truthy or ``timeout`` elapses.

    Swallows transient exceptions from the predicate (a stats read
    racing a restart is not a verdict) — only the final state decides.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    try:
        return bool(predicate())
    except Exception:
        return False


def stats_by_pid(opal, min_pids: int = 2, attempts: int = 200, interval: float = 0.05):
    """Sample the stats endpoint repeatedly; keep the LATEST snapshot per pid.

    Requests land on arbitrary workers, so repeated single-sample reads
    eventually observe each worker. Returns {pid: latest_stats} once min_pids
    distinct pids are seen (plus one grace sample for freshness), or after
    `attempts` samples; the caller decides whether the count is sufficient.
    """
    seen = {}
    grace_sweep_done = False
    for _ in range(attempts):
        snap = opal.stats(samples=1)
        seen[snap["pid"]] = snap
        if len(seen) >= min_pids:
            if grace_sweep_done:
                break
            grace_sweep_done = True
        time.sleep(interval)
    return seen


def list_seeded_repos(count: int) -> List[str]:
    return [f"policy-repo-{i:04d}" for i in range(count)]


# A reserved repo seeded *outside* the numeric ``policy-repo-NNNN`` range that
# ``list_seeded_repos`` enumerates, so no boot/leak test ever clones it. The
# resilience offline-hang test uses it as its "healthy" probe so the scope must
# perform a genuine *clone* through the starved executor, rather than reusing an
# on-disk clone left by another test (clones live at ``base_dir/<source_id>``
# keyed by URL-hash and survive ``compose restart/stop/start`` — opal_server
# mounts no volume at ``/opal``; only ``down -v`` wipes them). Note serving the
# bundle (``make_bundle`` via ``run_sync``) shares that same fetch executor, so a
# pre-cloned shared repo would be starved on serve too — the never-cloned probe
# is belt-and-suspenders that additionally exercises the clone path. Keep this
# name in sync with ``RESERVED_REPOS`` in ``seed/seed_gitea.py``.
HEALTHY_PROBE_REPO = "policy-repo-healthy-probe"
