import os
import sys

from opal_server.config import opal_server_config
from opal_server.debug_stats import git_fetcher_cache_stats
from opal_server.git_fetcher import GitPolicyFetcher


def test_stats_report_dict_sizes(monkeypatch):
    monkeypatch.setattr(GitPolicyFetcher, "repo_locks", {"a": object()})
    monkeypatch.setattr(GitPolicyFetcher, "repos", {"p1": object(), "p2": object()})
    monkeypatch.setattr(GitPolicyFetcher, "repos_last_fetched", {})

    stats = git_fetcher_cache_stats()

    assert stats["repo_locks"] == 1
    assert stats["repos"] == 2
    assert stats["repos_last_fetched"] == 0
    assert isinstance(stats["rss_kb"], int)
    # On Linux /proc/self/status exists, so RSS reading must actually work; on
    # other platforms _read_rss_kb falls back to 0 and the wiring is untestable.
    if sys.platform.startswith("linux"):
        assert stats["rss_kb"] > 0
    else:
        assert stats["rss_kb"] >= 0


def test_internal_stats_flag_defaults_off():
    assert opal_server_config.DEBUG_INTERNAL_STATS is False


def test_stats_include_pid_and_cache_keys(monkeypatch):
    monkeypatch.setattr(GitPolicyFetcher, "repos", {"/clones/x": object()})
    monkeypatch.setattr(GitPolicyFetcher, "repos_last_fetched", {"sid-1": "ts"})
    monkeypatch.setattr(GitPolicyFetcher, "repo_locks", {"sid-1": object()})

    stats = git_fetcher_cache_stats()

    assert stats["pid"] == os.getpid()
    assert stats["repos_keys"] == ["/clones/x"]
    assert stats["repos_last_fetched_keys"] == ["sid-1"]
    assert stats["repo_locks_keys"] == ["sid-1"]


class _ChurningDict(dict):
    """Simulates a dict being resized by another thread mid-iteration: any
    direct keys() iteration blows up; only an atomic .copy() snapshot is safe."""

    def keys(self):
        raise RuntimeError("dictionary changed size during iteration (simulated)")


def test_stats_survive_concurrent_cache_mutation(monkeypatch):
    monkeypatch.setattr(GitPolicyFetcher, "repos", _ChurningDict({"/c/x": object()}))
    monkeypatch.setattr(
        GitPolicyFetcher, "repos_last_fetched", _ChurningDict({"sid-1": "ts"})
    )
    monkeypatch.setattr(GitPolicyFetcher, "repo_locks", _ChurningDict({"sid-1": 1}))

    stats = git_fetcher_cache_stats()  # must not iterate the live dicts

    assert stats["repos_keys"] == ["/c/x"]
    assert stats["repo_locks_keys"] == ["sid-1"]
    assert stats["repos_last_fetched_keys"] == ["sid-1"]


def test_stats_counts_derive_from_the_same_snapshot_as_keys(monkeypatch):
    monkeypatch.setattr(GitPolicyFetcher, "repos", {"/c/a": object(), "/c/b": object()})
    monkeypatch.setattr(GitPolicyFetcher, "repos_last_fetched", {"s1": "t", "s2": "t"})
    monkeypatch.setattr(GitPolicyFetcher, "repo_locks", {"s1": object()})

    stats = git_fetcher_cache_stats()

    assert stats["repos"] == len(stats["repos_keys"]) == 2
    assert stats["repos_last_fetched"] == len(stats["repos_last_fetched_keys"]) == 2
    assert stats["repo_locks"] == len(stats["repo_locks_keys"]) == 1
