"""SCOPES_GIT_FETCH_BACKEND=cli: scope fetches through `git fetch` in a
killable process group (PER-17993).

Real fetches run against local origins with the real git. The kill, failure
and credential tests put a fake `git` first on PATH: a shell script that
records what it was given, then hangs or fails as the test needs.
"""

import base64
import os
import subprocess
import time
from pathlib import Path

import pygit2
import pytest
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    NoAuthData,
    SSHAuthData,
)
from opal_server import git_fetcher
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    FETCH_BACKEND_CLI,
    FETCH_BACKEND_PYGIT2,
    GitCliFetchError,
    GitPolicyFetcher,
    _cli_fetch,
    _cli_fetch_argv,
    fetch_backend,
    git_op_in_flight,
)


def _git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin"
    _git("init", "-q", "-b", "main", str(origin))
    for args in (
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "t"],
        ["commit", "-q", "--allow-empty", "-m", "c1"],
    ):
        _git("-C", str(origin), *args)
    return origin


def _loose_objects(clone: Path) -> set:
    objects = clone / ".git" / "objects"
    return {
        p.relative_to(objects)
        for d in objects.iterdir()
        if len(d.name) == 2
        for p in d.iterdir()
    }


def _head(repo: Path, ref: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def clear_fetcher_caches():
    def clear():
        GitPolicyFetcher.repos.clear()
        GitPolicyFetcher.repo_locks.clear()
        GitPolicyFetcher.repos_last_fetched.clear()
        GitPolicyFetcher.source_backoff.clear()

    clear()
    yield
    clear()


@pytest.fixture
def cli_backend(monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_BACKEND", FETCH_BACKEND_CLI
    )


def _fake_git(tmp_path: Path, monkeypatch, body: str) -> Path:
    """Put a `git` script running ``body`` first on PATH; returns its dir."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    script = bin_dir / "git"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


def _source(url="git@github.com:example/policy.git", auth=None):
    return GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="main",
        auth=auth or NoAuthData(auth_type="none"),
    )


# --- the setting ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("pygit2", FETCH_BACKEND_PYGIT2),
        ("cli", FETCH_BACKEND_CLI),
        (" CLI ", FETCH_BACKEND_CLI),
        ("", FETCH_BACKEND_PYGIT2),
        ("libgit3", FETCH_BACKEND_PYGIT2),
    ],
)
def test_the_backend_setting_is_normalised_and_defaults_to_pygit2(
    monkeypatch, value, expected
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_BACKEND", value)
    monkeypatch.setattr(git_fetcher, "_fetch_backend_warned", False)
    assert fetch_backend() == expected


def test_the_default_backend_is_pygit2():
    assert opal_server_config.SCOPES_GIT_FETCH_BACKEND == FETCH_BACKEND_PYGIT2


def test_the_fetch_argv_speaks_v2_without_tags_or_auto_gc():
    argv = _cli_fetch_argv("/usr/bin/git", "/clone", "origin", prune=False)
    assert argv[:3] == ["/usr/bin/git", "-C", "/clone"]
    for setting in (
        "protocol.version=2",
        "gc.auto=0",
        "maintenance.auto=false",
        "fetch.writeCommitGraph=false",
        "fetch.unpackLimit=1",
    ):
        assert argv[argv.index(setting) - 1] == "-c"
    assert argv[-1] == "origin"
    assert "--no-tags" in argv and "--prune" not in argv
    assert "--prune" in _cli_fetch_argv("/usr/bin/git", "/clone", "origin", True)


# --- real fetches --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_cli_fetch_brings_new_commits_into_the_clone(
    tmp_path, clear_fetcher_caches, cli_backend
):
    """End to end on a real clone of a local origin: the clone is made with
    pygit2, the fetch runs `git fetch`, and the remote-tracking ref and
    FETCH_HEAD move to the origin's new head."""
    origin = _origin(tmp_path)
    source = _source(url=str(origin))
    base = tmp_path / "base"
    fetcher = GitPolicyFetcher(base, "scope-1", source)
    clone = Path(GitPolicyFetcher.repo_clone_path(base, source))
    await fetcher.fetch_and_notify_on_changes()  # clones (pygit2)
    _git("-C", str(origin), "commit", "-q", "--allow-empty", "-m", "c2")
    new_head = _head(origin, "main")
    assert _head(clone, "refs/remotes/origin/main") != new_head
    loose_before = _loose_objects(clone)

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert _head(clone, "refs/remotes/origin/main") == new_head
    fetch_head = (clone / ".git" / "FETCH_HEAD").read_text()
    assert new_head in fetch_head
    assert not git_op_in_flight(fetcher._source_id)
    # One pack per fetch, as with libgit2: the fetch adds no loose objects
    # the repack (which counts packs) would never see.
    assert _loose_objects(clone) == loose_before


@pytest.mark.asyncio
async def test_a_cli_fetch_prunes_only_when_configured(
    tmp_path, clear_fetcher_caches, cli_backend, monkeypatch
):
    origin = _origin(tmp_path)
    _git("-C", str(origin), "branch", "gone")
    source = _source(url=str(origin))
    base = tmp_path / "base"
    fetcher = GitPolicyFetcher(base, "scope-1", source)
    clone = Path(GitPolicyFetcher.repo_clone_path(base, source))
    await fetcher.fetch_and_notify_on_changes()
    assert (clone / ".git" / "refs" / "remotes" / "origin" / "gone").exists() or (
        "refs/remotes/origin/gone" in (clone / ".git" / "packed-refs").read_text()
    )
    _git("-C", str(origin), "branch", "-D", "gone")

    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", False)
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    assert _head(clone, "refs/remotes/origin/gone")

    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_PRUNE", True)
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    with pytest.raises(subprocess.CalledProcessError):
        _head(clone, "refs/remotes/origin/gone")


# --- a stalled fetch is killed -------------------------------------------------


_HANG = """\
# A child in the same group, as git's ssh or index-pack would be.
sleep 60 &
echo $! > "$(dirname "$0")/child.pid"
echo $$ > "$(dirname "$0")/git.pid"
wait
"""


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    # A zombie still answers kill(0); only its parent (us, for git) reaps it.
    try:
        waited, _ = os.waitpid(pid, os.WNOHANG)
        return waited == pid
    except ChildProcessError:
        return False


def test_a_stalled_cli_fetch_is_killed_with_its_children(tmp_path, monkeypatch):
    bin_dir = _fake_git(tmp_path, monkeypatch, _HANG)
    start = time.monotonic()
    with pytest.raises(TimeoutError, match="exceeded 0.5s"):
        _cli_fetch(
            tmp_path, "origin", _source(), fetch_timeout=0.5, prune=False, term_grace=1
        )
    assert time.monotonic() - start < 5
    child = int((bin_dir / "child.pid").read_text())
    deadline = time.monotonic() + 5
    while not _gone(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _gone(child), "the fetch's child process outlived the kill"


@pytest.mark.asyncio
async def test_a_stalled_cli_fetch_frees_its_source_for_the_next_sync(
    tmp_path, clear_fetcher_caches, cli_backend, monkeypatch
):
    """Through fetch_and_notify_on_changes: the timed-out fetch is logged and
    backed off as with pygit2, but its busy key is released when it is
    killed, so the next sync fetches instead of logging "still running after
    its timeout". With pygit2 the hung fetch would hold it."""
    origin = _origin(tmp_path)
    source = _source(url=str(origin))
    base = tmp_path / "base"
    fetcher = GitPolicyFetcher(base, "scope-1", source)
    clone = Path(GitPolicyFetcher.repo_clone_path(base, source))
    await fetcher.fetch_and_notify_on_changes()  # clones with the real git
    real_path = os.environ["PATH"]
    _fake_git(tmp_path, monkeypatch, _HANG)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 0.5)
    monkeypatch.setattr(git_fetcher, "_CLI_FETCH_TERM_GRACE_SECONDS", 0.5)

    await fetcher.fetch_and_notify_on_changes(force_fetch=True)

    assert not git_op_in_flight(fetcher._source_id)
    assert GitPolicyFetcher.source_backoff[fetcher._source_id].consecutive_failures == 1

    monkeypatch.setenv("PATH", real_path)
    _git("-C", str(origin), "commit", "-q", "--allow-empty", "-m", "c2")
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    assert _head(clone, "refs/remotes/origin/main") == _head(origin, "main")
    assert fetcher._source_id not in GitPolicyFetcher.source_backoff


_IGNORE_TERM = """\
trap '' TERM
echo $$ > "$(dirname "$0")/git.pid"
while :; do sleep 1; done
"""


def test_a_git_that_ignores_sigterm_is_sigkilled(tmp_path, monkeypatch):
    bin_dir = _fake_git(tmp_path, monkeypatch, _IGNORE_TERM)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        _cli_fetch(
            tmp_path,
            "origin",
            _source(),
            fetch_timeout=0.5,
            prune=False,
            term_grace=0.5,
        )
    assert time.monotonic() - start < 5
    assert _gone(int((bin_dir / "git.pid").read_text()))


def test_a_git_that_outlives_its_sigkill_is_waited_for(tmp_path, monkeypatch):
    """Uninterruptible I/O: _stop_git reports git still running.

    _cli_fetch then waits for it rather than return, so the caller's
    executor timeout fires and the busy key stays held, as with a hung
    pygit2 fetch; a second fetch must not start on a clone git is still
    writing.
    """
    _fake_git(tmp_path, monkeypatch, "sleep 2\n")
    monkeypatch.setattr(git_fetcher, "_stop_git", lambda *a, **k: False)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        _cli_fetch(tmp_path, "origin", _source(), fetch_timeout=0.3, prune=False)
    assert time.monotonic() - start >= 1.9


# --- a failed fetch ------------------------------------------------------------


def test_a_failed_cli_fetch_is_a_git_error_with_credentials_masked(
    tmp_path, monkeypatch
):
    _fake_git(
        tmp_path,
        monkeypatch,
        "echo \"fatal: unable to access 'https://user:s3cret@git.example/x.git/'\" >&2\n"
        "exit 128\n",
    )
    with pytest.raises(GitCliFetchError) as err:
        _cli_fetch(tmp_path, "origin", _source(), fetch_timeout=5, prune=False)
    assert isinstance(err.value, pygit2.GitError)
    assert err.value.returncode == 128
    assert "fatal: unable to access" in err.value.stderr_tail
    assert "s3cret" not in err.value.stderr_tail and "s3cret" not in str(err.value)


def test_no_git_on_path_is_a_failed_fetch(tmp_path, monkeypatch):
    """A missing git is a GitError, so the source is counted and backed off
    instead of every sync raising FileNotFoundError."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(GitCliFetchError, match="git not found on PATH") as err:
        _cli_fetch(tmp_path, "origin", _source(), fetch_timeout=5, prune=False)
    assert isinstance(err.value, pygit2.GitError)


def test_no_temp_dir_for_the_key_is_a_failed_fetch(tmp_path, monkeypatch):
    _fake_git(tmp_path, monkeypatch, "exit 0\n")

    def _full(*a, **k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(git_fetcher.tempfile, "mkdtemp", _full)
    auth = SSHAuthData(username="git", private_key="K")
    with pytest.raises(GitCliFetchError, match="No space left"):
        _cli_fetch(tmp_path, "origin", _source(auth=auth), fetch_timeout=5, prune=False)


def test_sources_without_a_key_make_no_temp_dir(tmp_path, monkeypatch):
    _fake_git(tmp_path, monkeypatch, "exit 0\n")

    def _never(*a, **k):
        raise AssertionError("mkdtemp for a source without an SSH key")

    monkeypatch.setattr(git_fetcher.tempfile, "mkdtemp", _never)
    _cli_fetch(tmp_path, "origin", _source(), fetch_timeout=5, prune=False)
    _cli_fetch(
        tmp_path,
        "origin",
        _source(url="https://github.com/x/y.git", auth=GitHubTokenAuthData(token="t")),
        fetch_timeout=5,
        prune=False,
    )


def _old(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


@pytest.mark.parametrize("age, removed", [(10_000, True), (5, False)])
def test_a_stale_lock_a_killed_git_left_is_removed_once_old_enough(
    tmp_path, monkeypatch, age, removed
):
    """Git removes its locks on SIGTERM, not when SIGKILLed while holding one;
    every later fetch then fails on it.

    One older than the longest a CLI fetch lives belongs to no live
    fetch and is removed; a young one may be another worker's and stays.
    """
    clone = tmp_path / "clone"
    lock = clone / ".git" / "refs" / "remotes" / "origin" / "main.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("")
    _old(lock, age)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 150)
    _fake_git(
        tmp_path,
        monkeypatch,
        f"echo \"error: Unable to create '{lock}': File exists.\" >&2\nexit 1\n",
    )
    with pytest.raises(GitCliFetchError):
        _cli_fetch(clone, "origin", _source(), fetch_timeout=5, prune=False)
    assert lock.exists() is not removed


def test_a_lock_outside_the_clone_is_never_removed(tmp_path, monkeypatch):
    clone = tmp_path / "clone"
    (clone / ".git").mkdir(parents=True)
    elsewhere = tmp_path / "other.lock"
    elsewhere.write_text("")
    _old(elsewhere, 10_000)
    _fake_git(
        tmp_path,
        monkeypatch,
        f"echo \"error: Unable to create '{elsewhere}': File exists.\" >&2\nexit 1\n",
    )
    with pytest.raises(GitCliFetchError):
        _cli_fetch(clone, "origin", _source(), fetch_timeout=5, prune=False)
    assert elsewhere.exists()


# --- the repack sweep and a concurrent CLI fetch -----------------------------


@pytest.mark.parametrize(
    "backend, young_kept", [(FETCH_BACKEND_CLI, True), (FETCH_BACKEND_PYGIT2, False)]
)
def test_the_repack_sweep_spares_a_cli_fetchs_in_flight_files(
    tmp_path, monkeypatch, backend, young_kept
):
    """The repack lock does not cover fetches, and git's index-pack writes
    tmp_pack_* and installs its .pack before its .idx.

    With the CLI backend the sweep leaves such files until no live fetch
    can own them.
    """
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_BACKEND", backend)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 150)
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    young = ["tmp_pack_live", "pack-" + "a" * 40 + ".pack"]
    old = ["tmp_pack_dead", "pack-" + "b" * 40 + ".pack"]
    for name in young + old:
        (pack_dir / name).write_bytes(b"x")
    for name in old:
        _old(pack_dir / name, 10_000)

    git_fetcher._remove_repack_leftovers(pack_dir, "in a test")

    left = {p.name for p in pack_dir.iterdir()}
    assert not (set(old) & left)
    assert (set(young) <= left) is young_kept


# --- credentials ---------------------------------------------------------------


_RECORD = """\
out="$(dirname "$0")/record"
printf '%s\\n' "$@" > "$out.argv"
printf '%s' "$GIT_SSH_COMMAND" > "$out.ssh"
env > "$out.env"
key=$(printf '%s' "$GIT_SSH_COMMAND" | sed -n "s/.* -i '\\{0,1\\}\\([^' ]*\\)'\\{0,1\\}.*/\\1/p")
if [ -n "$key" ]; then
  cp "$key" "$out.key"
  stat -c '%a' "$key" > "$out.keymode" 2>/dev/null || stat -f '%Lp' "$key" > "$out.keymode"
  d=$(dirname "$key")
  stat -c '%a' "$d" > "$out.dirmode" 2>/dev/null || stat -f '%Lp' "$d" > "$out.dirmode"
  echo "$key" > "$out.keypath"
fi
"""


def test_an_ssh_key_reaches_ssh_through_a_private_file_never_argv(
    tmp_path, monkeypatch
):
    bin_dir = _fake_git(tmp_path, monkeypatch, _RECORD)
    key = "-----BEGIN OPENSSH PRIVATE KEY-----\nKEYDATA\n-----END OPENSSH PRIVATE KEY-----"
    auth = SSHAuthData(username="git", private_key=key)

    _cli_fetch(tmp_path, "origin", _source(auth=auth), fetch_timeout=5, prune=False)

    rec = bin_dir / "record"
    assert "KEYDATA" not in (bin_dir / "record.argv").read_text()
    ssh = (bin_dir / "record.ssh").read_text()
    for option in (
        "BatchMode=yes",
        "StrictHostKeyChecking=yes",
        "IdentitiesOnly=yes",
        "ServerAliveInterval=15",
        "ServerAliveCountMax=4",
    ):
        assert f"-o {option}" in ssh
    assert "KEYDATA" not in ssh
    assert (bin_dir / "record.key").read_text() == key + "\n"
    assert (bin_dir / "record.keymode").read_text().strip() == "600"
    assert (bin_dir / "record.dirmode").read_text().strip() == "700"
    key_path = Path((bin_dir / "record.keypath").read_text().strip())
    assert not key_path.exists() and not key_path.parent.exists()
    assert rec.with_suffix(".env").read_text().count("KEYDATA") == 0


def test_a_github_token_goes_in_the_environment_never_argv(tmp_path, monkeypatch):
    bin_dir = _fake_git(tmp_path, monkeypatch, _RECORD)
    auth = GitHubTokenAuthData(token="tok-123")

    _cli_fetch(
        tmp_path,
        "origin",
        _source(url="https://github.com/example/policy.git", auth=auth),
        fetch_timeout=5,
        prune=False,
    )

    assert "tok-123" not in (bin_dir / "record.argv").read_text()
    env = dict(
        line.split("=", 1)
        for line in (bin_dir / "record.env").read_text().splitlines()
        if "=" in line
    )
    expected = base64.b64encode(b"git:tok-123").decode()
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert env["GIT_CONFIG_VALUE_0"] == f"Authorization: Basic {expected}"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    # ssh keeps its options for every source, auth or not.
    assert "StrictHostKeyChecking=yes" in env["GIT_SSH_COMMAND"]


def test_the_key_dir_is_removed_even_when_the_fetch_fails(tmp_path, monkeypatch):
    bin_dir = _fake_git(tmp_path, monkeypatch, _RECORD + "exit 1\n")
    auth = SSHAuthData(username="git", private_key="K")
    with pytest.raises(GitCliFetchError):
        _cli_fetch(tmp_path, "origin", _source(auth=auth), fetch_timeout=5, prune=False)
    key_path = Path((bin_dir / "record.keypath").read_text().strip())
    assert not key_path.parent.exists()


def test_only_the_allowlisted_environment_reaches_git(tmp_path, monkeypatch):
    bin_dir = _fake_git(tmp_path, monkeypatch, _RECORD)
    monkeypatch.setenv("OPAL_SOME_SECRET", "do-not-pass")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/private-ca.pem")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    _cli_fetch(tmp_path, "origin", _source(), fetch_timeout=5, prune=False)
    env = (bin_dir / "record.env").read_text().splitlines()
    assert not any("do-not-pass" in line for line in env)
    assert "LC_ALL=C" in env
    # TLS trust and proxies, which libgit2 reads in-process, reach git too.
    assert "SSL_CERT_FILE=/etc/private-ca.pem" in env
    assert "HTTPS_PROXY=http://proxy.example:3128" in env
