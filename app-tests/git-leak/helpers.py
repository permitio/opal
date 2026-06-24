"""HTTP + infra helpers for the git-leak test bed."""
import subprocess
import time
from pathlib import Path
from typing import Dict, List

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

    def stats(self, samples: int = 3, interval: float = 0.1) -> Dict[str, int]:
        """Read the git-fetcher cache stats, merged across a few reads.

        The stack runs a single uvicorn worker (see docker-compose.yml), so the
        per-process ``GitPolicyFetcher`` caches are read deterministically — a
        read can't miss the worker that fetched. Sampling a few times and taking
        the ``max`` per key only smooths over a read that races an in-flight
        mutation; it is not relied on to paper over multi-worker nondeterminism
        (which the single-worker setup removes outright).
        """
        merged: Dict[str, int] = {}
        for i in range(max(1, samples)):
            resp = requests.get(
                f"{self.base_url}/internal/git-fetcher-cache-stats", timeout=10
            )
            resp.raise_for_status()
            for key, value in resp.json().items():
                merged[key] = max(merged.get(key, 0), value)
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
        compose("exec", "-T", "redis", "redis-cli", "FLUSHALL")
        compose("start", "opal_server")
        self._created_scopes.clear()
        self.wait_healthy(timeout=timeout)

    def delete_all_scopes(self, drain_timeout: int = 20) -> None:
        """Delete every scope the *server* knows (not just this client's), then
        best-effort wait for the caches to drain — a clean slate independent of
        what any prior, possibly-failed, test left behind.

        Best-effort drain by design: on master, delete never purges the caches
        (the leak this suite gates), so the wait simply times out. This runs in
        fixture setup/teardown, so a failure here must not mask the test, hence
        the broad excepts and bounded wait.
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
                if self.stats()["repo_locks"] == 0:
                    return
            except Exception:
                return
            time.sleep(1)

    def get_scope_policy(self, scope_id: str) -> requests.Response:
        """Fetch a scope's policy bundle (GET /scopes/{id}/policy).

        A 200 here proves the scope's repo was cloned and is being served —
        the signal that a healthy scope still works while another scope's
        clone is hanging.
        """
        return requests.get(
            f"{self.base_url}/scopes/{scope_id}/policy", timeout=30
        )

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
            json={"name": name, "private": False, "auto_init": True},
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


def compose(*args: str) -> subprocess.CompletedProcess:
    """Run `docker compose <args>`; on failure, surface the captured output.

    `capture_output=True` keeps compose noise out of passing tests, but a raw
    CalledProcessError shows only the exit code — so on failure we re-raise
    with the captured stdout/stderr embedded, otherwise a broken build/seed/
    restart is opaque to debug.
    """
    proc = subprocess.run(
        ["docker", "compose", *args],
        cwd=_COMPOSE_DIR,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"`docker compose {' '.join(args)}` failed (exit {proc.returncode})\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    return proc


def bounce_postgres(down_seconds: int = 5) -> None:
    compose("stop", "postgres")
    time.sleep(down_seconds)
    # `up -d --wait` blocks until Postgres passes its healthcheck again (plain
    # `compose start` has no --wait), so a recovery poll that follows isn't
    # racing an unready broadcaster. --no-recreate keeps the same container.
    compose("up", "-d", "--wait", "--no-recreate", "postgres")


def list_seeded_repos(count: int) -> List[str]:
    return [f"policy-repo-{i:04d}" for i in range(count)]
