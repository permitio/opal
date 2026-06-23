"""HTTP + infra helpers for the git-leak test bed."""
import subprocess
import time
from pathlib import Path
from typing import Dict, List

import requests

OPAL_URL = "http://localhost:7002"
GITEA_INTERNAL_URL = "http://gitea:3000"
GITEA_USER = "opaladmin"

# the compose project lives next to this file; compose() runs from here
_COMPOSE_DIR = str(Path(__file__).resolve().parent)


class OpalServerClient:
    def __init__(self, base_url: str = OPAL_URL):
        self.base_url = base_url.rstrip("/")

    def wait_healthy(self, timeout: int = 180) -> None:
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                if requests.get(f"{self.base_url}/healthcheck", timeout=5).status_code == 200:
                    return
            except requests.RequestException as exc:
                last = exc
            time.sleep(2)
        raise RuntimeError(f"opal-server not healthy in {timeout}s (last: {last})")

    def stats(self) -> Dict[str, int]:
        resp = requests.get(
            f"{self.base_url}/internal/git-fetcher-cache-stats", timeout=10
        )
        resp.raise_for_status()
        return resp.json()

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

    def delete_scope(self, scope_id: str) -> None:
        resp = requests.delete(f"{self.base_url}/scopes/{scope_id}", timeout=30)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()

    def refresh_all(self) -> None:
        # publishes a refresh on the webhook topic; leader pulls all scopes
        resp = requests.post(f"{self.base_url}/scopes/refresh", timeout=30)
        if resp.status_code == 404:
            return  # endpoint name differs across versions; caller falls back to poll
        resp.raise_for_status()


def gitea_repo_url(name: str) -> str:
    # url reachable from inside the opal_server container
    return f"{GITEA_INTERNAL_URL}/{GITEA_USER}/{name}.git"


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
