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

# TEST-NET-1 (RFC 5737): routable but runs no git server, so a clone hangs
# instead of failing fast — used to simulate an offline/unreachable repo.
UNREACHABLE_HOST = "192.0.2.1"

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

    def stats(self, samples: int = 5, interval: float = 0.1) -> Dict[str, int]:
        """Read the git-fetcher cache stats, merged across several reads.

        The server runs multiple workers and the ``GitPolicyFetcher`` caches
        are per-process, so a single read may land on a worker with empty
        caches (e.g. a non-leader that never fetched). Sample a few times and
        take the ``max`` per key, so the harness observes whichever worker
        still holds the most entries — this prevents both false negatives
        (missing a populated leader) and false positives (an ``== 0`` drain
        assertion passing only because it hit an empty worker).
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

    def cleanup_created_scopes(self, drain_timeout: int = 15) -> None:
        """Delete every scope created on this client, then best-effort wait for
        the caches to drain — so the next test starts from a clean slate.

        Best-effort by design: on master, delete never purges the caches (the
        leak this suite gates), so the drain wait will simply time out. A
        teardown failure must never fail the test that just ran, hence the broad
        excepts and the bounded wait.
        """
        for scope_id in list(self._created_scopes):
            try:
                self.delete_scope(scope_id)
            except Exception:
                self._created_scopes.discard(scope_id)
        deadline = time.time() + drain_timeout
        while time.time() < deadline:
            try:
                if self.stats(samples=1)["repos"] == 0:
                    return
            except Exception:
                return
            time.sleep(1)

    def refresh_all(self) -> None:
        # Best-effort: POST /scopes/refresh publishes on the webhook topic so
        # every leader re-syncs all scopes. If this OPAL build doesn't expose
        # the route (404), treat it as a no-op — there is no client-side
        # fallback; callers rely on their own stats polling either way.
        resp = requests.post(f"{self.base_url}/scopes/refresh", timeout=30)
        if resp.status_code == 404:
            return
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
    """Return a git URL for ``name`` pointing at a routable-but-dead host.

    Simulates an offline/unreachable policy repo: the address is in
    TEST-NET-1 (RFC 5737), which is routable but runs no git server, so a
    clone hangs rather than failing fast — exercising the missing fetch
    timeout on the scopes path (the bug PR3 fixes). The URL keeps the same
    ``/{user}/{name}.git`` shape as a real Gitea repo so the scope looks
    ordinary apart from the unreachable host.
    """
    return f"http://{UNREACHABLE_HOST}/{GITEA_USER}/{name}.git"


def compose(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=_COMPOSE_DIR,
        capture_output=True,
        text=True,
        check=True,
    )


def bounce_postgres(down_seconds: int = 5) -> None:
    compose("stop", "postgres")
    time.sleep(down_seconds)
    compose("start", "postgres")


def list_seeded_repos(count: int) -> List[str]:
    return [f"policy-repo-{i:04d}" for i in range(count)]
