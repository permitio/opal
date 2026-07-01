"""Read-only introspection of the git-fetcher in-memory caches.

Used only by the off-by-default /internal stats endpoint so tests can
observe the cache growth that the memory-leak fix (PR2) eliminates.
"""
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, params
from opal_server.git_fetcher import GitPolicyFetcher


def _read_rss_kb() -> int:
    """Resident set size of this process in kilobytes (Linux), else 0."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def git_fetcher_cache_stats() -> Dict[str, int]:
    """Sizes of the three process-global GitPolicyFetcher caches + RSS."""
    return {
        "repo_locks": len(GitPolicyFetcher.repo_locks),
        "repos": len(GitPolicyFetcher.repos),
        "repos_last_fetched": len(GitPolicyFetcher.repos_last_fetched),
        "rss_kb": _read_rss_kb(),
    }


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
    def _git_fetcher_cache_stats() -> Dict[str, int]:
        return git_fetcher_cache_stats()
