"""Read-only introspection of the git-fetcher in-memory caches.

Used only by the off-by-default /internal stats endpoint so tests can
observe the cache growth that the memory-leak fix (PR2) eliminates.
"""
import collections
import gc
import os
import tracemalloc
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygit2
from fastapi import FastAPI, Query, params
from opal_server.git_fetcher import GitPolicyFetcher

# How many allocation sites to report. Enough to see a culprit stand out from
# the interpreter's own baseline, short enough to read in a terminal.
_TRACEMALLOC_TOP = 15


def _read_rss_kb() -> int:
    """Resident set size of this process in kilobytes (Linux), else 0."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def _libgit2_cache_bytes() -> Optional[Tuple[int, int]]:
    """Libgit2's own object cache as (used, max) bytes.

    The one suspect here that no Python tool can see: it is a native allocation,
    so it never appears in gc, in tracemalloc, or in an object census. Capped at
    256 MB by default and never tuned in this repo, which makes it a bounded
    contributor rather than an unbounded leak -- but bounded-and-full still hides
    a quarter gigabyte from every other number on this endpoint.

    Returns None rather than raising when pygit2 does not expose it, because a
    diagnostic endpoint that 500s on an older pygit2 is worse than one that says
    it cannot see the value.
    """
    try:
        used, maximum = pygit2.settings.cached_memory
        return int(used), int(maximum)
    except Exception:
        return None


def _tracemalloc_stats() -> Dict:
    """Top Python allocation sites, when the operator has tracing on.

    Deliberately does NOT start tracing: tracemalloc roughly doubles the
    interpreter's allocation bookkeeping, which is not a decision this endpoint
    should make for a running production worker. Start it out of band with
    PYTHONTRACEMALLOC=<frames> in the environment -- stdlib, no code change --
    and this reports what it found.

    `tracing: False` is reported distinctly from a zero measurement: "not
    looking" and "looked, found nothing" are different answers, and conflating
    them would let a leak hide behind an unstarted tracer.
    """
    if not tracemalloc.is_tracing():
        return {"tracing": False}

    traced, peak = tracemalloc.get_traced_memory()
    top = [
        {
            "location": str(stat.traceback),
            "size_kb": stat.size // 1024,
            "count": stat.count,
        }
        for stat in tracemalloc.take_snapshot().statistics("lineno")[:_TRACEMALLOC_TOP]
    ]
    return {
        "tracing": True,
        "traced_kb": traced // 1024,
        "peak_kb": peak // 1024,
        "top": top,
    }


def _object_census(top_n: int) -> List[Dict]:
    """Live Python objects grouped by type, biggest first.

    Catches a growing container the named cache counters do not cover.
    It walks every tracked object while holding the GIL, so on a multi-
    GB worker this is a stall rather than a stat -- hence opt-in per
    request, never on by default.
    """
    counts = collections.Counter(type(obj).__name__ for obj in gc.get_objects())
    return [{"type": name, "count": count} for name, count in counts.most_common(top_n)]


def git_fetcher_cache_stats(top_objects: int = 0) -> Dict:
    """Sizes + keys of the three process-global GitPolicyFetcher caches, RSS,
    and the worker pid (per-process caches: the pid identifies WHICH worker
    answered, so multi-worker bed tests can assert per-worker drain)."""
    # Snapshot each cache once (dict.copy() is a single C-level operation,
    # atomic under the GIL): this handler runs on a Starlette worker thread
    # while the caches are mutated on the event-loop/executor threads, so
    # iterating the live dicts can raise "dictionary changed size during
    # iteration", and reading len() and keys() separately can return a
    # self-contradictory count/keys pair.
    repo_locks = GitPolicyFetcher.repo_locks.copy()
    repos = GitPolicyFetcher.repos.copy()
    repos_last_fetched = GitPolicyFetcher.repos_last_fetched.copy()
    stats: Dict = {
        "pid": os.getpid(),
        "repo_locks": len(repo_locks),
        "repos": len(repos),
        "repos_last_fetched": len(repos_last_fetched),
        "rss_kb": _read_rss_kb(),
        "repo_locks_keys": sorted(repo_locks.keys()),
        "repos_keys": sorted(repos.keys()),
        "repos_last_fetched_keys": sorted(repos_last_fetched.keys()),
        "libgit2_cache_bytes": _libgit2_cache_bytes(),
        "tracemalloc": _tracemalloc_stats(),
    }
    if top_objects > 0:
        stats["object_counts"] = _object_census(top_objects)
    return stats


def register_internal_stats_route(
    app: FastAPI,
    enabled: bool,
    dependencies: Optional[List[params.Depends]] = None,
) -> None:
    """Mount GET /internal/git-fetcher-cache-stats only when enabled.

    ``dependencies`` are applied to the route (e.g. the server's
    ``JWTAuthenticator``) so the endpoint is protected when JWT verification
    is enabled. When verification is disabled — as in the test bed, which
    leaves ``OPAL_AUTH_PUBLIC_KEY`` unset — the authenticator is a no-op and
    the route stays reachable without a token.
    """
    if not enabled:
        return

    # Deliberately a sync def: Starlette runs it in its own threadpool, which is
    # independent of the default loop executor opal uses for git fetches
    # (run_sync -> run_in_executor(None, ...)). So this endpoint keeps answering
    # even when hung clones saturate the fetch executor — which is exactly the
    # condition the offline-repo test observes through it.
    @app.get(
        "/internal/git-fetcher-cache-stats",
        include_in_schema=False,
        dependencies=dependencies or [],
    )
    def _git_fetcher_cache_stats(
        top_objects: int = Query(
            0,
            ge=0,
            description=(
                "Include the top N live object types from a gc census. "
                "Walks every tracked object under the GIL, so leave it at 0 "
                "unless you are actively hunting a growing container."
            ),
        ),
    ) -> Dict:
        return git_fetcher_cache_stats(top_objects=top_objects)
