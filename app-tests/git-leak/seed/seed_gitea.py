"""Seed a Gitea instance with N policy repos for the OPAL git-leak test bed.

Idempotent: re-running creates only the missing repos. Each repo gets a
single commit containing a minimal OPA policy tree.

Env:
  GITEA_URL            e.g. http://gitea:3000
  GITEA_ADMIN_USER     admin username (created out-of-band by compose)
  GITEA_ADMIN_PASSWORD admin password
  REPO_COUNT           how many repos to ensure exist (default 50)
"""
import os
import sys
import time
from pathlib import Path

import requests
from git import Actor, Repo

POLICY_REGO = """package example

default allow = false

allow {
    input.user == "admin"
}
"""

DATA_JSON = '{"roles": {"admin": ["read", "write"]}}\n'


def _wait_for_gitea(base_url: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{base_url}/api/v1/version", timeout=5).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError(f"Gitea not reachable at {base_url} within {timeout}s")


def _ensure_token(base_url: str, user: str, password: str) -> str:
    name = "seed-token"
    resp = requests.post(
        f"{base_url}/api/v1/users/{user}/tokens",
        auth=(user, password),
        json={"name": name, "scopes": ["write:repository", "write:user"]},
        timeout=10,
    )
    if resp.status_code == 201:
        return resp.json()["sha1"]
    # token already exists -> delete then recreate (Gitea won't reveal an existing secret)
    requests.delete(
        f"{base_url}/api/v1/users/{user}/tokens/{name}",
        auth=(user, password),
        timeout=10,
    )
    resp = requests.post(
        f"{base_url}/api/v1/users/{user}/tokens",
        auth=(user, password),
        json={"name": name, "scopes": ["write:repository", "write:user"]},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["sha1"]


def _ensure_repo(base_url: str, token: str, user: str, name: str) -> None:
    headers = {"Authorization": f"token {token}"}
    exists = requests.get(
        f"{base_url}/api/v1/repos/{user}/{name}", headers=headers, timeout=10
    )
    if exists.status_code == 200:
        return
    created = requests.post(
        f"{base_url}/api/v1/user/repos",
        headers=headers,
        json={"name": name, "private": False, "auto_init": False},
        timeout=10,
    )
    created.raise_for_status()


def _push_policy(
    base_url: str, token: str, user: str, name: str, workdir: Path
) -> None:
    repo_dir = workdir / name
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "example.rego").write_text(POLICY_REGO)
    (repo_dir / "data.json").write_text(DATA_JSON)

    repo = Repo.init(repo_dir, initial_branch="main")
    repo.index.add(["example.rego", "data.json"])
    author = Actor("seed", "seed@example.com")
    repo.index.commit("seed policy", author=author, committer=author)

    push_url = (
        base_url.replace("http://", f"http://{user}:{token}@") + f"/{user}/{name}.git"
    )
    origin = repo.create_remote("origin", push_url)
    origin.push(refspec="main:main")


def main() -> int:
    base_url = os.environ["GITEA_URL"].rstrip("/")
    user = os.environ["GITEA_ADMIN_USER"]
    password = os.environ["GITEA_ADMIN_PASSWORD"]
    count = int(os.environ.get("REPO_COUNT", "50"))

    _wait_for_gitea(base_url)
    token = _ensure_token(base_url, user, password)

    workdir = Path("/tmp/seed-work")
    for i in range(count):
        name = f"policy-repo-{i:04d}"
        _ensure_repo(base_url, token, user, name)
        # only push if the repo is empty (freshly created)
        head = requests.get(
            f"{base_url}/api/v1/repos/{user}/{name}/branches/main",
            headers={"Authorization": f"token {token}"},
            timeout=10,
        )
        if head.status_code != 200:
            _push_policy(base_url, token, user, name, workdir)
        print(f"seeded {name}", flush=True)

    # write the token where the test harness can read it
    Path("/seed-output/token").write_text(token)
    print(f"DONE: ensured {count} repos", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
