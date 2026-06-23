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
    assert stats["rss_kb"] >= 0


def test_internal_stats_flag_defaults_off():
    assert opal_server_config.DEBUG_INTERNAL_STATS is False
