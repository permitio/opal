"""The policy repo watcher's change notification is built off the event loop.

Outside scopes mode the watcher of POLICY_REPO_URL diffs the old and new
commits (or walks the tree) through git processes before it publishes.
On the event loop that stalls every request the worker serves for as
long as the diff is large. A sleep stands in for a large diff.
"""

import asyncio
import threading
import time
from pathlib import Path

import git
import pytest
from opal_common.git_utils.diff_viewer import DiffViewer
from opal_server.policy.watcher import callbacks
from opal_server.policy.watcher.callbacks import publish_changed_directories

AUTHOR = git.Actor("test", "test@example.com")
SLOW_SECONDS = 0.5
MAX_LAG_SECONDS = 0.15


class _Publisher:
    def __init__(self):
        self.published = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def publish(self, topics, data=None):
        self.published.append(topics)


def _commit(repo: git.Repo, relpath: str, contents: str) -> git.Commit:
    path = Path(repo.working_tree_dir) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    repo.index.add([relpath])
    return repo.index.commit(f"update {relpath}", author=AUTHOR, committer=AUTHOR)


@pytest.mark.asyncio
async def test_the_diff_never_stalls_the_event_loop(tmp_path, monkeypatch):
    """Mutation: diffing on the loop (no run_sync) fails here."""
    init = DiffViewer.__init__

    def _slow_diff(self, *args, **kwargs):
        time.sleep(SLOW_SECONDS)
        init(self, *args, **kwargs)

    monkeypatch.setattr(DiffViewer, "__init__", _slow_diff)
    publisher = _Publisher()
    loop = asyncio.get_running_loop()
    lags = []
    done = asyncio.Event()

    async def _tick():
        while not done.is_set():
            started = loop.time()
            await asyncio.sleep(0.01)
            lags.append(loop.time() - started - 0.01)

    with git.Repo.init(tmp_path / "repo") as repo:
        old = _commit(repo, "policy/a.rego", "package a\n")
        new = _commit(repo, "policy/a.rego", "package a\n\ndefault allow := false\n")
        ticker = asyncio.create_task(_tick())
        await asyncio.sleep(0.03)
        try:
            await publish_changed_directories(old, new, publisher, [".rego"])
        finally:
            done.set()
            await ticker

    assert publisher.published == [["policy:.", "policy:policy"]]
    assert max(lags) < MAX_LAG_SECONDS, f"the event loop stalled {max(lags):.2f}s"


@pytest.mark.asyncio
async def test_the_diff_runs_on_a_repo_of_its_own(tmp_path, monkeypatch):
    """The thread reads the clone through a Repo opened for it: the watcher's
    own Repo, which a webhook's pull may use on the loop meanwhile, is never
    touched off the loop.

    Mutation: handing the watcher's own commits to the thread fails here.
    """
    seen = []
    build = callbacks.create_policy_update

    def _recording(old, new, *args, **kwargs):
        seen.append((old.repo, new.repo, threading.get_ident()))
        return build(old, new, *args, **kwargs)

    monkeypatch.setattr(callbacks, "create_policy_update", _recording)
    publisher = _Publisher()

    with git.Repo.init(tmp_path / "repo") as repo:
        old = _commit(repo, "policy/a.rego", "package a\n")
        new = _commit(repo, "policy/a.rego", "package a\n\ndefault allow := false\n")
        await publish_changed_directories(old, new, publisher, [".rego"])

    [(old_repo, new_repo, thread)] = seen
    assert old_repo is new_repo and old_repo is not repo
    assert thread != threading.get_ident()
    assert publisher.published == [["policy:.", "policy:policy"]]
