"""Seed a Gitea instance with N policy repos for the OPAL git-leak test bed.

Idempotent: re-running creates only the missing repos. Each repo gets a
single commit containing a minimal OPA policy tree.

Env:
  GITEA_URL            e.g. http://gitea:3000
  GITEA_ADMIN_USER     admin username (created out-of-band by compose)
  GITEA_ADMIN_PASSWORD admin password
  REPO_COUNT           how many repos to ensure exist (default 50)
  MAIN_REPO_BRANCHES   if set and >0, ALSO create one repo named
                       ``shared-policy`` and push this many branches to it
                       (``branch-0000``..``branch-<K-1>``). Demonstrates the
                       prod-dominant boot shape (one shared repo, many
                       branches) that SCOPES_REPO_CLONES_SHARDS caps, as
                       opposed to the distinct-repo shape the existing
                       numeric ``policy-repo-NNNN`` set exercises. Additive:
                       leaves the numeric seeding untouched when unset.

                       Content shape (prod-representative multi-tenant
                       policy repo, NOT fully-distinct-per-branch): a single
                       shared BASE commit lands on ``main`` first —
                       MAIN_REPO_REGO_FILES .rego modules of
                       MAIN_REPO_REGO_FILE_KB each, identical across every
                       branch because every branch shares that one commit in
                       its history (git stores those blobs ONCE for the
                       whole repo, not once per branch). Each branch then
                       adds exactly one small, branch-distinct
                       ``tenants/tenant_<idx>/data.json`` diff on top of
                       ``main`` (target size MAIN_REPO_DATA_JSON_KB, jittered
                       per branch into the ~20-50KB range) and is pushed as
                       its own ref — real shared-history + small-per-branch-
                       tip, not K independent orphan trees.
  MAIN_REPO_REGO_FILES    number of shared base .rego files (default 40)
  MAIN_REPO_REGO_FILE_KB  target size (KB) of each shared base .rego file
                       (default 25 -> ~1MB shared base across all branches)
  MAIN_REPO_DATA_JSON_KB  target center size (KB) of each branch's own small
                       tenant data.json diff (default 35; actual per-branch
                       size is jittered into ~20-50KB, deterministic off the
                       branch index)
                       Together these make the repo prod-realistic in shape:
                       one big shared history + many small per-branch tips,
                       so per-branch bundle/sync cost is measurable rather
                       than ~1ms, without exaggerating clone size the way a
                       fully-distinct-per-branch tree would. See
                       test_boot_sharding_demo.py.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
from git import Actor, Repo

POLICY_REGO = """package example

default allow = false

allow {
    input.user == "admin"
}
"""

DATA_JSON = '{"roles": {"admin": ["read", "write"]}}\n'

# Reserved repos seeded in addition to the numeric ``policy-repo-NNNN`` set.
# These sit outside the range the boot/leak tests enumerate (so no test ever
# clones them) and back the resilience offline-hang test's "healthy" probe,
# which must force a fresh clone through the saturated executor rather than
# reuse a surviving on-disk clone. Keep in sync with ``HEALTHY_PROBE_REPO`` in
# ``helpers.py``.
RESERVED_REPOS = ("policy-repo-healthy-probe",)

# The single repo the main-tier (shared-repo, many-branches) seed mode pushes
# to. Keep in sync with any test/helper that builds its URL.
MAIN_REPO_NAME = "shared-policy"


def _base_rego_module_content(file_idx: int, target_bytes: int) -> str:
    """A syntactically-valid shared base .rego module, padded with
    deterministic (but NOT branch-indexed) comment lines to approximately
    ``target_bytes``.

    Deliberately identical for every branch: this content is committed once
    to ``main`` and every branch shares that commit in its history, so git
    stores these blobs ONCE for the whole repo — the "common base" half of
    the prod-representative shape (see module docstring). Content-identical
    across branches is the point here, the mirror image of the old
    fully-distinct design.
    """
    header = (
        f"package shard_demo.base.mod_{file_idx:03d}\n\n"
        "default allow = false\n\n"
        "allow {\n"
        f"    input.module == {file_idx}\n"
        "    input.user == data.roles.admin_users[_]\n"
        "}\n\n"
    )
    pad_lines = []
    size = len(header)
    i = 0
    while size < target_bytes:
        token = hashlib.sha256(f"base-{file_idx}-{i}".encode()).hexdigest()
        line = f"# pad-{token}\n"
        pad_lines.append(line)
        size += len(line)
        i += 1
    return header + "".join(pad_lines)


def _base_files(rego_file_count: int, rego_file_kb: int) -> dict:
    """The {relative_path: content} set for the ONE shared base commit on
    ``main``: many identical-across-branches .rego modules plus a shared roles
    data file the per-branch tenant diffs build on top of."""
    files = {
        f"policies/mod_{file_idx:03d}.rego": _base_rego_module_content(
            file_idx, rego_file_kb * 1024
        )
        for file_idx in range(rego_file_count)
    }
    files["data.json"] = DATA_JSON
    return files


def _tenant_data_json_content(branch_idx: int, target_kb_center: int) -> str:
    """A small, per-branch DISTINCT ``tenants/tenant_<idx>/data.json`` diff —
    the only content that differs branch-to-branch in this shape.

    Sized to ``target_kb_center`` KB, jittered deterministically (off the
    branch index) into the ~20-50KB tenant-diff range this mode targets,
    rather than every branch landing on the exact same byte count.
    """
    jitter_kb = (
        int(hashlib.sha256(f"tenant-jitter-{branch_idx}".encode()).hexdigest(), 16) % 15
    )
    target_kb = max(20, min(50, target_kb_center - 7 + jitter_kb))
    target_bytes = target_kb * 1024

    obj = {
        "branch": f"{branch_idx:04d}",
        "tenant": {"id": branch_idx, "name": f"tenant-{branch_idx:04d}"},
        "records": [],
    }
    overhead = len(json.dumps(obj))
    # ~ observed bytes per record entry (id + 64-hex-char hash + JSON
    # punctuation); used only to size the record count, not for exactness.
    approx_record_bytes = 100
    count = max(1, (target_bytes - overhead) // approx_record_bytes)
    obj["records"] = [
        {"id": i, "hash": hashlib.sha256(f"{branch_idx}-{i}".encode()).hexdigest()}
        for i in range(count)
    ]
    return json.dumps(obj) + "\n"


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


def _data_json_for(name: str) -> str:
    """Per-repo DISTINCT policy data.

    Every repo used to get byte-identical content, and the commit is made with a
    fixed author/message, so a repo's sha depended only on the wall-clock second
    it was pushed in — 20 repos pushed in a loop routinely share one. Two repos
    with the same sha serve byte-identical bundles, which silently breaks any
    test that distinguishes repos by served content: the precondition of
    ``test_scope_repoint_releases_old_repo_cache`` ("the scope switched to
    serving repo_b") can then never become true, and the gate burns its 300s poll
    and fails without ever reaching the cache-drain assertion it exists for.
    Embedding the repo name makes the tree — and therefore the sha — unique.
    """
    return DATA_JSON.replace("}}", '}, "repo": "%s"}' % name)


def _push_policy(
    base_url: str, token: str, user: str, name: str, workdir: Path
) -> None:
    repo_dir = workdir / name
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "example.rego").write_text(POLICY_REGO)
    (repo_dir / "data.json").write_text(_data_json_for(name))

    repo = Repo.init(repo_dir, initial_branch="main")
    repo.index.add(["example.rego", "data.json"])
    author = Actor("seed", "seed@example.com")
    repo.index.commit("seed policy", author=author, committer=author)

    # Inject credentials scheme-agnostically (works for http and https) rather
    # than string-replacing "http://", which would silently drop the creds if
    # GITEA_URL were ever https and produce an opaque auth failure.
    parts = urlsplit(base_url)
    push_url = urlunsplit(
        (parts.scheme, f"{user}:{token}@{parts.netloc}", f"/{user}/{name}.git", "", "")
    )
    origin = repo.create_remote("origin", push_url)
    origin.push(refspec="main:main")


def _existing_branches(base_url: str, token: str, user: str, name: str) -> set:
    headers = {"Authorization": f"token {token}"}
    branches = set()
    page = 1
    while True:
        resp = requests.get(
            f"{base_url}/api/v1/repos/{user}/{name}/branches",
            headers=headers,
            params={"page": page, "limit": 50},
            timeout=10,
        )
        if resp.status_code != 200:
            break
        batch = resp.json()
        if not batch:
            break
        branches.update(b["name"] for b in batch)
        page += 1
    return branches


def _push_main_repo_branches(
    base_url: str,
    token: str,
    user: str,
    name: str,
    workdir: Path,
    branch_count: int,
    rego_file_count: int,
    rego_file_kb: int,
    data_json_kb: int,
) -> None:
    """Ensure ``main`` carries the one shared base commit (see
    ``_base_files``), then push ``branch_count`` branches
    (``branch-0000``..``branch-<K-1>``) to ``name``, each just ``main`` plus
    one small, branch-DISTINCT tenant ``data.json`` diff (see
    ``_tenant_data_json_content``) — shared history + small per-branch tips,
    prod-representative of a real multi-tenant policy repo (see module
    docstring), instead of K independent, fully-distinct orphan trees.

    Idempotent: the base commit is only (re)created if ``main`` doesn't
    already exist on the remote, and only branches missing on the remote are
    created/pushed — so a re-run (or a larger ``MAIN_REPO_BRANCHES`` than a
    prior run) tops up rather than recreates. Note this means the
    content-size knobs (``MAIN_REPO_REGO_FILES`` etc.) only apply to a
    *fresh* ``main``/newly-created branches; changing them and re-running
    does NOT resize an already-seeded base or branch set (start from a
    fresh ``docker compose down -v`` to change content size).
    """
    wanted = [f"branch-{i:04d}" for i in range(branch_count)]
    existing = _existing_branches(base_url, token, user, name)
    missing = [b for b in wanted if b not in existing]

    repo_dir = workdir / name
    repo_dir.mkdir(parents=True, exist_ok=True)

    author = Actor("seed", "seed@example.com")
    if (repo_dir / ".git").exists():
        repo = Repo(repo_dir)
    else:
        repo = Repo.init(repo_dir, initial_branch="main")

    parts = urlsplit(base_url)
    push_url = urlunsplit(
        (parts.scheme, f"{user}:{token}@{parts.netloc}", f"/{user}/{name}.git", "", "")
    )
    try:
        origin = repo.remote("origin")
        origin.set_url(push_url)
    except ValueError:
        origin = repo.create_remote("origin", push_url)

    if "main" in existing:
        # Shared base already pushed by a prior run/container — sync local
        # `main` to it (rather than re-seeding) so a fresh workdir topping up
        # extra branches still branches off the SAME base commit.
        repo.git.fetch("origin", "main")
        repo.git.checkout("-B", "main", "origin/main")
    else:
        repo.git.checkout("-B", "main")
        base_files = _base_files(rego_file_count, rego_file_kb)
        paths = []
        for rel_path, content in base_files.items():
            fpath = repo_dir / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
            paths.append(rel_path)
        repo.index.add(paths)
        repo.index.commit("seed shared base policy", author=author, committer=author)
        origin.push(refspec="main:main")
        base_kb = rego_file_count * rego_file_kb
        print(
            f"{name}: seeded shared base on main "
            f"({rego_file_count} rego files, ~{base_kb}KB total)",
            flush=True,
        )

    if not missing:
        print(f"{name}: all {branch_count} branches already present", flush=True)
        return

    print(
        f"{name}: seeding {len(missing)} branches, each = shared main base + "
        f"one ~{data_json_kb}KB-centered (20-50KB jittered) tenant data.json diff",
        flush=True,
    )

    for branch in missing:
        idx = int(branch.split("-", 1)[1])
        # Branch off `main` (shared history), NOT --orphan: every branch's
        # tree starts as exactly main's tree, so checking it out here also
        # resets the working dir back to just the base content — no manual
        # _clear_workdir dance needed the way the old orphan design required.
        repo.git.checkout("-b", branch, "main")

        tenant_path = f"tenants/tenant_{idx:04d}/data.json"
        content = _tenant_data_json_content(idx, data_json_kb)
        fpath = repo_dir / tenant_path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)

        repo.index.add([tenant_path])
        repo.index.commit(f"seed {branch} tenant data", author=author, committer=author)
        origin.push(refspec=f"{branch}:{branch}")
        print(f"seeded {name}@{branch} (base + {tenant_path})", flush=True)


def main() -> int:
    base_url = os.environ["GITEA_URL"].rstrip("/")
    user = os.environ["GITEA_ADMIN_USER"]
    password = os.environ["GITEA_ADMIN_PASSWORD"]
    count = int(os.environ.get("REPO_COUNT", "50"))

    _wait_for_gitea(base_url)
    token = _ensure_token(base_url, user, password)

    workdir = Path("/tmp/seed-work")
    failures = []
    # the numeric set the boot/leak tests enumerate, plus the reserved repos
    # (e.g. the resilience offline-hang test's never-cloned healthy probe)
    names = [f"policy-repo-{i:04d}" for i in range(count)] + list(RESERVED_REPOS)
    for name in names:
        # Isolate per-repo failures: one bad push must not abort the loop and
        # leave an indeterminate subset seeded. Collect failures and exit
        # non-zero with a count so the harness sees a real seed error (and
        # `docker compose wait seed` surfaces it) instead of a later, confusing
        # load-gate timeout.
        try:
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
        except Exception as exc:  # noqa: BLE001 - report, don't abort the loop
            failures.append((name, repr(exc)))
            print(f"FAILED {name}: {exc!r}", flush=True)

    total = len(names)
    if failures:
        print(
            f"ERROR: seeded {total - len(failures)}/{total} repos; "
            f"{len(failures)} failed (e.g. {failures[:3]})",
            flush=True,
        )
        return 1

    main_repo_branches = int(os.environ.get("MAIN_REPO_BRANCHES", "0"))
    if main_repo_branches > 0:
        rego_file_count = int(os.environ.get("MAIN_REPO_REGO_FILES", "40"))
        rego_file_kb = int(os.environ.get("MAIN_REPO_REGO_FILE_KB", "2"))
        data_json_kb = int(os.environ.get("MAIN_REPO_DATA_JSON_KB", "200"))
        try:
            _ensure_repo(base_url, token, user, MAIN_REPO_NAME)
            _push_main_repo_branches(
                base_url,
                token,
                user,
                MAIN_REPO_NAME,
                workdir,
                main_repo_branches,
                rego_file_count,
                rego_file_kb,
                data_json_kb,
            )
        except (
            Exception
        ) as exc:  # noqa: BLE001 - report, don't mask a hard seed failure
            print(f"ERROR: {MAIN_REPO_NAME} branch seeding failed: {exc!r}", flush=True)
            return 1

    print(f"DONE: ensured {total} repos", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
