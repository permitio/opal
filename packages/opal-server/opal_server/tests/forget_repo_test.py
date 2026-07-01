from opal_server.git_fetcher import GitPolicyFetcher


class _FakeRepo:
    def __init__(self):
        self.freed = False

    def free(self):
        self.freed = True


def test_forget_repo_pops_and_frees(monkeypatch):
    fake = _FakeRepo()
    monkeypatch.setattr(GitPolicyFetcher, "repos", {"/clones/x": fake})

    GitPolicyFetcher.forget_repo("/clones/x")

    assert "/clones/x" not in GitPolicyFetcher.repos
    assert fake.freed is True


def test_forget_repo_unknown_path_is_noop(monkeypatch):
    monkeypatch.setattr(GitPolicyFetcher, "repos", {})
    GitPolicyFetcher.forget_repo("/clones/missing")  # must not raise
    assert GitPolicyFetcher.repos == {}


def test_forget_repo_without_free_method(monkeypatch):
    monkeypatch.setattr(GitPolicyFetcher, "repos", {"/clones/y": object()})
    GitPolicyFetcher.forget_repo("/clones/y")  # object() has no .free(); must not raise
    assert "/clones/y" not in GitPolicyFetcher.repos
