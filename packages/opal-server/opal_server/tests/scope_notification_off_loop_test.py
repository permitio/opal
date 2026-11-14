"""A scope's change notification is built off the event loop.

When a scope's branch moved, or on its first sync or a repoint, the leader
opens the scope's clone with GitPython and diffs the two heads, or walks
the whole tree of the head to name every policy directory. That reads the
clone through git processes for as long as the diff or the tree is large:
a walk of a 20,000-file tree took 120-160 ms. On the event loop it stalls
every request the worker serves, the scope's own bundle requests included,
for that long. A ticker on the loop measures the stall while a clone that
is slow to walk or diff (a sleep stands in for the size of the tree)
builds the notification.
"""

import asyncio
import threading
import time
from pathlib import Path

import git
import pytest
from opal_common.git_utils.commit_viewer import CommitViewer
from opal_common.git_utils.diff_viewer import DiffViewer
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes.service import NewCommitsCallbacks

SCOPE_ID = "s1"
AUTHOR = git.Actor("test", "test@example.com")
# How long the slow clone takes to walk or diff, and the most the loop may lag
# meanwhile: on the loop the lag is the whole build.
SLOW_SECONDS = 0.5
MAX_LAG_SECONDS = 0.15
TICK_SECONDS = 0.01


class RecordingPubSub:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append((topics, data))


def _commit(repo: git.Repo, relpath: str, contents: str) -> git.Commit:
    path = Path(repo.working_tree_dir) / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    repo.index.add([relpath])
    return repo.index.commit(f"update {relpath}", author=AUTHOR, committer=AUTHOR)


@pytest.fixture
def scope_clone(tmp_path):
    """The scope's clone, where NewCommitsCallbacks looks for it, with two
    commits that change one policy file."""
    source = GitPolicyScopeSource(
        source_type="git",
        url="https://git.example.com/org/policy.git",
        auth=NoAuthData(),
    )
    with git.Repo.init(GitPolicyFetcher.repo_clone_path(tmp_path, source)) as repo:
        old = _commit(repo, "policy/a.rego", "package a\n")
        new = _commit(repo, "policy/a.rego", "package a\n\ndefault allow := false\n")
        return source, old.hexsha, new.hexsha


@pytest.fixture
def slow_clone(monkeypatch):
    """A clone that takes SLOW_SECONDS to walk or diff, as a large one does."""
    files = CommitViewer.files
    diff_viewer_init = DiffViewer.__init__

    def _slow_files(self, *args, **kwargs):
        time.sleep(SLOW_SECONDS)
        return files(self, *args, **kwargs)

    def _slow_diff(self, *args, **kwargs):
        time.sleep(SLOW_SECONDS)
        diff_viewer_init(self, *args, **kwargs)

    monkeypatch.setattr(CommitViewer, "files", _slow_files)
    monkeypatch.setattr(DiffViewer, "__init__", _slow_diff)


async def _max_loop_lag_during(coro) -> float:
    """How late, at most, a loop tick woke while ``coro`` ran."""
    loop = asyncio.get_running_loop()
    lags = []
    done = asyncio.Event()

    async def _tick():
        while not done.is_set():
            started = loop.time()
            await asyncio.sleep(TICK_SECONDS)
            lags.append(loop.time() - started - TICK_SECONDS)

    ticker = asyncio.create_task(_tick())
    await asyncio.sleep(TICK_SECONDS * 3)
    try:
        await coro
    finally:
        done.set()
        await ticker
    return max(lags)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["first sync", "moved branch", "repoint"], ids=lambda c: c
)
async def test_building_the_notification_never_stalls_the_event_loop(
    tmp_path, scope_clone, slow_clone, change
):
    """Mutation: building the notification on the loop (no run_sync in
    on_update) lags the loop by the whole build and fails here."""
    source, old, new = scope_clone
    pubsub = RecordingPubSub()
    callbacks = NewCommitsCallbacks(
        tmp_path, SCOPE_ID, source, pubsub, notify_all=change == "repoint"
    )
    previous = {"first sync": None, "moved branch": old, "repoint": new}[change]

    lag = await _max_loop_lag_during(callbacks.on_update(previous, new))

    [(topics, update)] = pubsub.published
    assert sorted(topics) == [f"{SCOPE_ID}:policy:.", f"{SCOPE_ID}:policy:policy"]
    assert update.new_policy_hash == new
    assert lag < MAX_LAG_SECONDS, (
        f"the event loop stalled {lag:.2f}s while the notification was built"
    )


@pytest.mark.asyncio
async def test_an_unmoved_head_builds_nothing(tmp_path, scope_clone, monkeypatch):
    """Every pass checks every scope: one whose head did not move opens no
    clone and publishes nothing."""
    source, _, new = scope_clone
    pubsub = RecordingPubSub()
    callbacks = NewCommitsCallbacks(tmp_path, SCOPE_ID, source, pubsub)

    def _no_repo(*args, **kwargs):
        raise AssertionError("the clone was opened for a head that did not move")

    monkeypatch.setattr(git, "Repo", _no_repo)

    await callbacks.on_update(new, new)

    assert pubsub.published == []


@pytest.mark.asyncio
async def test_a_cancelled_sync_waits_for_the_build_to_be_done_with_the_clone(
    tmp_path, scope_clone, monkeypatch
):
    """The thread building the notification cannot be stopped: a cancel of the
    sync waits for it, so that the sync's lock on the clone is not let go
    while git processes still read the clone.

    Mutation: a cancel that does not wait for the build ends first here.
    """
    source, old, new = scope_clone
    files = CommitViewer.files
    built = []

    def _slow_files(self, *args, **kwargs):
        time.sleep(SLOW_SECONDS)
        found = files(self, *args, **kwargs)
        built.append(time.monotonic())
        return found

    monkeypatch.setattr(CommitViewer, "files", _slow_files)
    callbacks = NewCommitsCallbacks(tmp_path, SCOPE_ID, source, RecordingPubSub())
    sync = asyncio.ensure_future(callbacks.on_update(None, new))
    await asyncio.sleep(SLOW_SECONDS / 5)

    sync.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sync
    ended = time.monotonic()

    assert built and built[0] <= ended


@pytest.mark.asyncio
async def test_at_most_two_notifications_are_built_at_once(
    tmp_path, scope_clone, monkeypatch
):
    """Builds run on a pool of their own of 2 threads, not on the default
    executor's many, so that a pass's builds leave bundle requests their
    threads and most of the GIL.

    Mutation: building on the default executor runs 5 at once here.
    """
    source, old, new = scope_clone
    files = CommitViewer.files
    running, most = [0], [0]
    lock = threading.Lock()

    def _counted(self, *args, **kwargs):
        with lock:
            running[0] += 1
            most[0] = max(most[0], running[0])
        try:
            time.sleep(0.2)
            return files(self, *args, **kwargs)
        finally:
            with lock:
                running[0] -= 1

    monkeypatch.setattr(CommitViewer, "files", _counted)
    pubsub = RecordingPubSub()
    syncs = [
        NewCommitsCallbacks(tmp_path, f"s{i}", source, pubsub).on_update(None, new)
        for i in range(5)
    ]

    await asyncio.gather(*syncs)

    assert len(pubsub.published) == 5
    assert most[0] == 2
