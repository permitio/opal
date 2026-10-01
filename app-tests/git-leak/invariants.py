"""Quiescence invariants I1-I6 for the git-leak bed.

Asserted at every test's teardown (see the ``opal`` fixture) after
``delete_all_scopes()``, and callable mid-test. Red-gate tests that
knowingly leave violations exempt specific IDs via
``@pytest.mark.invariant_exempt("I1", ...)``.

Deviation from the design spec: I1's "none missing" direction is NOT
asserted — scopes clone lazily, so a just-created scope legitimately has
no dir yet. Only the orphan direction (dir with no live scope) signals a
leak.
"""
import hashlib

import requests
from helpers import compose

BASE_DIR_IN_CONTAINER = "/opal/git_sources"


def source_id(url: str, branch: str = "main", shards: int = 1) -> str:
    """Host-side mirror of GitPolicyFetcher.source_id (sha256(url) + shard)."""
    base = hashlib.sha256(url.encode("utf-8")).hexdigest()
    index = hashlib.sha256(branch.encode("utf-8")).digest()[0] % shards
    return f"{base}-{index}"


def clone_dirs(service: str = "opal_server") -> set:
    out = compose(
        "exec",
        "-T",
        service,
        "sh",
        "-c",
        f"ls -1 {BASE_DIR_IN_CONTAINER} 2>/dev/null || true",
    ).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def live_source_ids(opal, shards: int = 1) -> set:
    resp = requests.get(f"{opal.base_url}/scopes", timeout=30)
    resp.raise_for_status()
    return {
        source_id(s["policy"]["url"], s["policy"].get("branch", "main"), shards)
        for s in resp.json()
    }


def check_invariants(opal, exempt=frozenset(), shards: int = 1) -> None:
    exempt = set(exempt)
    failures = []
    live = live_source_ids(opal, shards)
    disk = clone_dirs()
    stats = opal.stats(samples=1)

    if "I1" not in exempt:
        orphans = disk - live
        if orphans:
            failures.append(
                f"I1: {len(orphans)} orphan clone dir(s) on disk, e.g. {sorted(orphans)[:3]}"
            )
    if "I2" not in exempt:
        cached_dirs = {k.rsplit("/", 1)[-1] for k in stats.get("repos_keys", [])}
        stray = cached_dirs - disk
        if stray:
            failures.append(
                f"I2: cached repo handle(s) with no dir on disk: {sorted(stray)[:3]}"
            )
    if "I3" not in exempt:
        stray = set(stats.get("repos_last_fetched_keys", [])) - live
        if stray:
            failures.append(
                f"I3: repos_last_fetched key(s) with no live scope: {sorted(stray)[:3]}"
            )
    if "I4" not in exempt:
        stray = set(stats.get("repo_locks_keys", [])) - live
        if stray:
            failures.append(
                f"I4: repo_locks key(s) with no live scope: {sorted(stray)[:3]}"
            )
    if "I6" not in exempt:
        if requests.get(f"{opal.base_url}/scopes", timeout=10).status_code != 200:
            failures.append("I6: scopes API not answering 200")

    assert not failures, (
        "invariant violations:\n  "
        + "\n  ".join(failures)
        + f"\nstats={stats}\ndisk(sample)={sorted(disk)[:10]}"
    )
