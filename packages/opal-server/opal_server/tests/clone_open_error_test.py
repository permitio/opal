"""A sync that cannot open its scope clone.

Re-cloning a clone of a repository with tens of thousands of branches
takes minutes, during which every scope on it answers 503 or 409. So a
clone is deleted and cloned again only when opening it says it is not a
repository or is corrupt (pygit2.GitError, a missing head object). An
error of the server's own side while opening it (too many open files, a
permission, any OSError) is logged with the clone's path, the sync is
skipped, and the clone is kept for the next sync to retry.
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pygit2
import pytest
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.tests.redaction_fixtures import capture_logs
from opal_server.git_fetcher import GitPolicyFetcher, PolicyFetcherCallbacks

_DELETIONS = "opal_server.scopes.clone_deletions"


class _Updates(PolicyFetcherCallbacks):
    def __init__(self):
        self.updates = []

    async def on_update(self, old_head, head):
        self.updates.append((old_head, head))


# pygit2 opens every scope clone, whichever backend fetches it. The child
# interpreter of test_too_many_open_files_keeps_the_clone gets the backend
# through OPAL_SCOPES_GIT_FETCH_WITH_CLI.
pytestmark = pytest.mark.fetch_backend("both")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    for name in ("repos", "repos_last_fetched", "repo_locks", "source_backoff"):
        monkeypatch.setattr(GitPolicyFetcher, name, {})


@pytest.fixture
def emitted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        metrics, "increment", lambda m, tags=None: calls.append((m, tags))
    )
    monkeypatch.setattr(metrics, "gauge", lambda m, v, tags=None: None)
    return calls


def _deletions(calls):
    return [tags for metric, tags in calls if metric == _DELETIONS]


def _commit(origin, text):
    sig = pygit2.Signature("opal-test", "opal-test@example.com")
    builder = origin.TreeBuilder()
    builder.insert(
        "policy.rego", origin.create_blob(text.encode()), pygit2.GIT_FILEMODE_BLOB
    )
    ref = "refs/heads/main"
    parents = [origin.references[ref].target] if ref in origin.references else []
    return str(origin.create_commit(ref, sig, sig, text, builder.write(), parents))


async def _cloned(tmp_path):
    """A local origin, and a fetcher whose clone of it has landed."""
    origin = pygit2.init_repository(str(tmp_path / "origin"), bare=True)
    _commit(origin, "package p\n")
    origin.set_head("refs/heads/main")
    source = GitPolicyScopeSource(
        source_type="git",
        url=str(tmp_path / "origin"),
        branch="main",
        auth=NoAuthData(auth_type="none"),
    )
    fetcher = GitPolicyFetcher(tmp_path / "base", "s1", source, callbacks=_Updates())
    await fetcher.fetch_and_notify_on_changes()
    assert (fetcher._repo_path / ".git").is_dir()
    return origin, fetcher


def _inode(path: Path) -> int:
    return os.stat(path).st_ino


def _object_dirs(git_dir: Path, which: str) -> list:
    objects = git_dir / "objects"
    if which == "fan-out":
        fanout = [d for d in objects.iterdir() if d.is_dir() and len(d.name) == 2]
        assert fanout, "the clone has no loose objects: the case proves nothing"
        return fanout
    return [objects / which if which else objects]


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a directory it cannot")
@pytest.mark.parametrize(
    "unreadable", ["pack", "", "fan-out"], ids=["pack", "objects", "fan-out"]
)
@pytest.mark.asyncio
async def test_an_unreadable_object_store_keeps_the_clone_and_skips_the_sync(
    tmp_path, emitted, unreadable
):
    """A directory of the object store this server cannot read. For
    objects/pack pygit2 raises OSError (Permission denied); for objects/ or a
    loose object's fan-out directory libgit2 reads the commit as not found,
    which is no missing commit. The clone stays, the sync is skipped with a
    WARNING naming the clone, and once it can be read the next sync syncs.

    Mutation: deleting the clone on that OSError, letting it out of the
    sync, or judging the commit missing without checking the directories,
    fails here.
    """
    origin, fetcher = await _cloned(tmp_path)
    git_dir = fetcher._repo_path / ".git"
    before = _inode(git_dir)
    new_head = _commit(origin, "package p\n# two\n")
    GitPolicyFetcher.repos.clear()  # a fresh open, as in another process
    dirs = _object_dirs(git_dir, unreadable)
    for directory in dirs:
        directory.chmod(0)
    try:
        with capture_logs() as logs:
            await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    finally:
        for directory in dirs:
            directory.chmod(0o755)

    assert _inode(git_dir) == before, "the clone was deleted"
    assert _deletions(emitted) == []
    assert [
        tags
        for metric, tags in emitted
        if metric == "opal_server.scopes.git_op_skipped"
    ] == [{"reason": "clone_unreadable"}]
    warnings = [
        json.loads(line)["record"]
        for line in logs.serialized
        if json.loads(line)["record"]["level"]["name"] == "WARNING"
    ]
    assert any(
        str(fetcher._repo_path) in w["message"] and "Permission denied" in w["message"]
        for w in warnings
    ), [w["message"] for w in warnings]

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    assert fetcher.callbacks.updates[-1][1] == new_head
    assert _inode(git_dir) == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root removes a directory it cannot read")
@pytest.mark.asyncio
async def test_a_delete_that_leaves_files_behind_is_not_followed_by_a_clone(
    tmp_path, emitted
):
    """A corrupt clone whose delete cannot finish (a directory in it this
    server cannot read): the next clone would fail into a directory that is
    still there, and back the source off for a fault of this server's. It is
    not attempted; an ERROR names the path.

    Mutation: cloning after a delete that failed fails here.
    """
    _origin, fetcher = await _cloned(tmp_path)
    git_dir = fetcher._repo_path / ".git"
    (git_dir / "config").write_text("[core\nbroken")
    stuck = git_dir / "info"
    stuck.mkdir(exist_ok=True)
    (stuck / "kept").write_text("")
    stuck.chmod(0)
    GitPolicyFetcher.repos.clear()
    try:
        with capture_logs() as logs:
            await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    finally:
        stuck.chmod(0o755)

    assert fetcher.clone_source_id not in GitPolicyFetcher.source_backoff
    failures = [
        tags
        for metric, tags in emitted
        if metric == "opal_server.scopes.git_op_failures"
    ]
    assert failures == [], "a clone was tried into what the delete left"
    errors = [
        json.loads(line)["record"]["message"]
        for line in logs.serialized
        if json.loads(line)["record"]["level"]["name"] == "ERROR"
    ]
    assert any(str(fetcher._repo_path) in e for e in errors), errors


_EMFILE_SCRIPT = textwrap.dedent(
    """
    import asyncio, json, os, resource, sys
    from pathlib import Path

    from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
    from opal_server.git_fetcher import GitPolicyFetcher

    base, url = sys.argv[1], sys.argv[2]
    source = GitPolicyScopeSource(
        source_type="git", url=url, branch="main", auth=NoAuthData(auth_type="none")
    )
    fetcher = GitPolicyFetcher(Path(base), "s1", source)
    git_dir = fetcher._repo_path / ".git"
    before = os.stat(git_dir).st_ino

    async def main():
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(soft, 512), hard))
        held = []
        try:
            while True:
                held.append(os.open(os.devnull, os.O_RDONLY))
        except OSError:
            pass
        try:
            await fetcher.fetch_and_notify_on_changes(force_fetch=True)
            outcome = "returned"
        except BaseException as exc:
            outcome = repr(exc)
        finally:
            for fd in held:
                os.close(fd)
        return outcome

    outcome = asyncio.run(main())
    print(json.dumps({
        "outcome": outcome,
        "kept": git_dir.is_dir() and os.stat(git_dir).st_ino == before,
    }))
    """
)


@pytest.mark.asyncio
async def test_too_many_open_files_keeps_the_clone(tmp_path, fetch_backend):
    """The process has no file descriptor left when the sync opens its clone
    (EMFILE, real, in a process of its own): the clone is kept and the sync
    returns, with a WARNING naming the clone."""
    _origin, fetcher = await _cloned(tmp_path)
    env = dict(
        os.environ,
        DD_TRACE_ENABLED="false",
        OPAL_SCOPES_GIT_FETCH_WITH_CLI="true" if fetch_backend == "cli" else "false",
    )
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            _EMFILE_SCRIPT,
            str(tmp_path / "base"),
            str(tmp_path / "origin"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result == {"outcome": "returned", "kept": True}, done.stderr[-2000:]
    assert str(fetcher._repo_path) in done.stderr
    assert "Too many open files" in done.stderr


@pytest.mark.asyncio
async def test_a_clone_that_is_not_a_repository_is_deleted_and_cloned_again(
    tmp_path, emitted
):
    """A config git cannot parse: pygit2 says the repository is unusable
    (GitError). The clone is deleted, counted with its reason, and cloned
    again."""
    origin, fetcher = await _cloned(tmp_path)
    (fetcher._repo_path / ".git" / "config").write_text("[core\nbroken")
    GitPolicyFetcher.repos.clear()

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert _deletions(emitted) == [{"reason": "invalid"}]
    repo = pygit2.Repository(str(fetcher._repo_path))
    try:
        assert str(repo.references["refs/remotes/origin/main"].target) == str(
            origin.references["refs/heads/main"].target
        )
    finally:
        repo.free()


@pytest.mark.asyncio
async def test_a_clone_missing_its_head_object_is_deleted_and_counted(
    tmp_path, emitted, monkeypatch
):
    """Refs intact, the object the branch names gone: corrupt beyond use."""
    origin, fetcher = await _cloned(tmp_path)
    git_dir = fetcher._repo_path / ".git"
    head = str(origin.references["refs/heads/main"].target)
    (git_dir / "objects").rename(tmp_path / "objects-moved-away")
    (git_dir / "objects").mkdir()
    (git_dir / "objects" / "pack").mkdir()
    GitPolicyFetcher.repos.clear()

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert _deletions(emitted) == [{"reason": "missing_object"}]
    repo = pygit2.Repository(str(fetcher._repo_path))
    try:
        assert repo.get(head) is not None
    finally:
        repo.free()


@pytest.mark.asyncio
async def test_a_deletion_is_counted_only_once_it_happened(tmp_path, emitted):
    """A corrupt clone another process's git op holds the lock of is not
    deleted, and not counted; once the lock is free the next sync deletes it,
    counts it once and clones it again.

    Mutation: counting before the delete counts the skipped one too.
    """
    from opal_server import git_cli

    _origin, fetcher = await _cloned(tmp_path)
    (fetcher._repo_path / ".git" / "config").write_text("[core\nbroken")
    GitPolicyFetcher.repos.clear()
    held = git_cli.take_clone_lock(fetcher._repo_path)
    assert held is not None
    try:
        await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    finally:
        git_cli.drop_clone_lock(held)
    assert _deletions(emitted) == []
    assert (fetcher._repo_path / ".git" / "config").read_text() == "[core\nbroken"

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    assert _deletions(emitted) == [{"reason": "invalid"}]
    pygit2.Repository(str(fetcher._repo_path)).free()
