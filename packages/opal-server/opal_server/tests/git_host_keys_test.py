"""SSH host keys of scope sources: trusted on first use by default, on both
fetch backends, or checked against SCOPES_GIT_SSH_KNOWN_HOSTS when it is set.

The first SSH fetch or clone records the host's key (the git command line in a
file beside each clone, libgit2 in one file per BASE_DIR, through
ssh-keyscan); a later op refuses a different key, counted with reason
host_key, backed off and logged with the file to reset. Every test runs
against a local sshd, and skips without one.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pygit2
import pytest
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, SSHAuthData
from opal_server import git_cli
from opal_server import git_fetcher as git_fetcher_module
from opal_server.config import opal_server_config
from opal_server.git_cli import (
    GitCliLocalError,
    host_key_record,
    validate_git_cli_settings,
)
from opal_server.git_fetcher import (
    LIBGIT2_HOME,
    GitCallback,
    GitPolicyFetcher,
    PolicyFetcherCallbacks,
    libgit2_known_hosts,
    prepare_libgit2_ssh,
    ssh_host_port,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("ssh-keyscan") is None,
    reason="needs git and ssh-keyscan",
)


class _Recorder(PolicyFetcherCallbacks):
    def __init__(self) -> None:
        self.updates = []

    async def on_update(self, old_head, head):
        self.updates.append((old_head, head))


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """Fresh fetcher state, scopes on, host keys trusted on first use, and
    libgit2's home (process-wide) put back after the test."""
    for name in ("repos", "repos_last_fetched", "repo_locks", "source_backoff"):
        monkeypatch.setattr(GitPolicyFetcher, name, {})
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path / "base"))
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.5)
    home = pygit2.settings.homedir
    yield
    pygit2.settings.homedir = home


@pytest.fixture
def emitted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        metrics, "increment", lambda m, tags=None: calls.append((m, tags))
    )
    monkeypatch.setattr(metrics, "gauge", lambda m, v, tags=None: None)
    return calls


@pytest.fixture
def log_lines():
    records = []
    sink = logger.add(lambda m: records.append(m.record), level="DEBUG")

    def _lines(level: str):
        return [r["message"] for r in records if r["level"].name == level]

    yield _lines
    logger.remove(sink)


def _failures(calls):
    return [
        tags for metric, tags in calls if metric == "opal_server.scopes.git_op_failures"
    ]


def _source(sshd, origin) -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git",
        url=sshd.url(origin.path),
        branch="master",
        auth=SSHAuthData(username="git", private_key=sshd.client_key),
    )


def _base() -> Path:
    return Path(opal_server_config.BASE_DIR)


def _record(source: GitPolicyScopeSource, backend: str) -> Path:
    """Where ``backend`` records the host keys ``source``'s ops check."""
    clone = GitPolicyFetcher.repo_clone_path(_base(), source)
    if backend == "cli":
        return host_key_record(clone)
    return libgit2_known_hosts(clone.parent)


def _name(sshd) -> str:
    return f"[127.0.0.1]:{sshd.port}"


async def _sync(source: GitPolicyScopeSource, scope_id: str = "scope-1"):
    fetcher = GitPolicyFetcher(_base(), scope_id, source, callbacks=_Recorder())
    await fetcher.fetch_and_notify_on_changes(force_fetch=True)
    return fetcher


def _key_of(record: Path, sshd) -> set:
    """The key types and keys ``record`` holds for the sshd."""
    found = set()
    for line in record.read_text().splitlines():
        names, key_type, key = line.split()[:3]
        if _name(sshd) in names.split(","):
            found.add(f"{key_type} {key}")
    return found


@pytest.mark.fetch_backend("both")
@pytest.mark.asyncio
async def test_the_first_op_records_the_host_key_and_later_ones_pass(
    fetch_backend, sshd, make_origin, tmp_path, emitted, log_lines
):
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)

    first = await _sync(source)
    head = origin.commit("master")
    second = await _sync(source)

    assert _failures(emitted) == []
    assert first.callbacks.updates and second.callbacks.updates[-1][1] == head
    record = _record(source, fetch_backend)
    assert sshd.public_key("host_key") in _key_of(record, sshd)
    recorded = [m for m in log_lines("INFO") if "Recorded the SSH host key" in m]
    assert recorded == [
        f"Recorded the SSH host key of {_name(sshd)} for "
        f"{GitPolicyFetcher.source_id(source)} in {record}"
    ]


@pytest.mark.fetch_backend("both")
@pytest.mark.parametrize("op", ["clone", "fetch"])
@pytest.mark.asyncio
async def test_a_changed_host_key_is_refused_and_backed_off(
    op, fetch_backend, sshd, make_origin, tmp_path, emitted, log_lines
):
    """The record holds another key for the host: the host changed its key
    since it was recorded. The op is refused, with reason host_key, the
    source is backed off, and the ERROR names the file to reset."""
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)
    record = _record(source, fetch_backend)
    if op == "fetch":
        await _sync(source)
        assert _failures(emitted) == []
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(f"{_name(sshd)} {sshd.public_key('other_host_key')}\n")
    origin.commit("master")

    fetcher = await _sync(source)

    assert _failures(emitted) == [{"op": op, "reason": "host_key"}]
    assert GitPolicyFetcher.source_id(source) in GitPolicyFetcher.source_backoff
    assert fetcher.callbacks.updates == []
    assert record.read_text() == f"{_name(sshd)} {sshd.public_key('other_host_key')}\n"
    errors = [m for m in log_lines("ERROR") if "SSH key was refused" in m]
    assert len(errors) == 1 and str(record) in errors[0], errors


@pytest.mark.fetch_backend("both")
@pytest.mark.asyncio
async def test_deleting_the_record_lets_the_next_op_record_the_host_key_again(
    fetch_backend, sshd, make_origin, tmp_path, emitted
):
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)
    record = _record(source, fetch_backend)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(f"{_name(sshd)} {sshd.public_key('other_host_key')}\n")
    await _sync(source)
    assert _failures(emitted) == [{"op": "clone", "reason": "host_key"}]

    record.unlink()
    GitPolicyFetcher.source_backoff.clear()
    fetcher = await _sync(source)

    assert _failures(emitted) == [{"op": "clone", "reason": "host_key"}]
    assert fetcher.callbacks.updates
    assert _key_of(record, sshd) == {sshd.public_key("host_key")}


@pytest.mark.fetch_backend("cli")
@pytest.mark.asyncio
async def test_an_empty_record_is_no_record_and_the_first_op_fills_and_logs_it(
    sshd, make_origin, tmp_path, emitted, log_lines
):
    """A record file with nothing in it (a write that never happened) holds no
    host key: the op that records one logs it."""
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)
    record = _record(source, "cli")
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text("")

    await _sync(source)

    assert _failures(emitted) == []
    assert _key_of(record, sshd) == {sshd.public_key("host_key")}
    recorded = [m for m in log_lines("INFO") if "Recorded the SSH host key" in m]
    assert recorded == [
        f"Recorded the SSH host key of {_name(sshd)} for "
        f"{GitPolicyFetcher.source_id(source)} in {record}"
    ]


@pytest.mark.fetch_backend("both")
@pytest.mark.asyncio
async def test_a_reclone_keeps_the_recorded_host_key(
    fetch_backend, sshd, make_origin, tmp_path, emitted
):
    """The record is beside the clone, not in it: cloning again (an invalid
    clone, a re-clone at start) does not reset the trust."""
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)
    await _sync(source)
    record = _record(source, fetch_backend)
    kept = record.read_text()
    clone = GitPolicyFetcher.repo_clone_path(_base(), source)
    GitPolicyFetcher.forget_repo(str(clone))
    shutil.rmtree(clone)

    fetcher = await _sync(source)

    assert fetcher.callbacks.updates
    assert record.read_text() == kept
    record.write_text(f"{_name(sshd)} {sshd.public_key('other_host_key')}\n")
    GitPolicyFetcher.forget_repo(str(clone))
    shutil.rmtree(clone)
    await _sync(source)
    assert _failures(emitted) == [{"op": "clone", "reason": "host_key"}]


@pytest.mark.fetch_backend("cli")
@pytest.mark.asyncio
async def test_with_the_git_command_line_each_clone_has_its_own_record(
    sshd, make_origin, tmp_path
):
    first = _source(sshd, make_origin(tmp_path / "served" / "one.git"))
    second = _source(sshd, make_origin(tmp_path / "served" / "two.git"))

    await _sync(first, "one")
    await _sync(second, "two")

    records = {_record(first, "cli"), _record(second, "cli")}
    assert len(records) == 2
    for record in records:
        assert _key_of(record, sshd) == {sshd.public_key("host_key")}


@pytest.mark.fetch_backend("libgit2")
@pytest.mark.asyncio
async def test_libgit2_records_a_host_s_keys_with_ssh_keyscan_once(
    sshd, make_origin, tmp_path, monkeypatch
):
    """Every key ssh-keyscan reads from the host, once per host and port for
    every source on it."""
    calls = tmp_path / "keyscan.argv"
    real = shutil.which("ssh-keyscan")
    shims = tmp_path / "bin"
    shims.mkdir()
    (shims / "ssh-keyscan").write_text(
        f'#!/bin/sh\necho "$@" >> "{calls}"\nexec "{real}" "$@"\n'
    )
    (shims / "ssh-keyscan").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    first = _source(sshd, make_origin(tmp_path / "served" / "one.git"))
    second = _source(sshd, make_origin(tmp_path / "served" / "two.git"))

    await _sync(first, "one")
    await _sync(second, "two")

    assert calls.read_text().splitlines() == [
        f"-T 10 -p {sshd.port} -t ed25519,ecdsa,rsa -- 127.0.0.1"
    ]
    store = _record(first, "libgit2")
    assert store == _base() / "git_sources" / LIBGIT2_HOME / ".ssh" / "known_hosts"
    assert sshd.public_key("host_key") in _key_of(store, sshd)
    assert pygit2.settings.homedir == str(store.parent.parent)


@pytest.mark.fetch_backend("libgit2")
@pytest.mark.asyncio
async def test_libgit2_without_ssh_keyscan_fails_ssh_sources_as_local(
    sshd, make_origin, tmp_path, monkeypatch, emitted, log_lines
):
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("git", "sh"):
        (bin_dir / tool).symlink_to(shutil.which(tool))
    monkeypatch.setenv("PATH", str(bin_dir))

    validate_git_cli_settings()
    await _sync(source)

    assert [m for m in log_lines("ERROR") if "no ssh-keyscan on PATH" in m]
    assert _failures(emitted) == [{"op": "clone", "reason": "local"}]
    assert not GitPolicyFetcher.repo_clone_path(_base(), source).exists()


@pytest.mark.fetch_backend("both")
@pytest.mark.parametrize(
    "listed, accepted",
    [
        ("this host, its key", True),
        ("another host only", False),
        ("another key", False),
    ],
)
@pytest.mark.asyncio
async def test_with_a_known_hosts_file_only_its_hosts_and_keys_are_accepted(
    listed, accepted, fetch_backend, sshd, make_origin, tmp_path, monkeypatch, emitted
):
    """SCOPES_GIT_SSH_KNOWN_HOSTS wins over trust on first use, on both
    backends: nothing is recorded, and the file is never written to."""
    path = tmp_path / "known_hosts"
    contents = {
        "this host, its key": f"{_name(sshd)} {sshd.public_key('host_key')}\n",
        "another host only": (
            f"[127.0.0.2]:{sshd.port} {sshd.public_key('host_key')}\n"
        ),
        "another key": f"{_name(sshd)} {sshd.public_key('other_host_key')}\n",
    }[listed]
    path.write_text(contents)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path))
    validate_git_cli_settings()
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)

    fetcher = await _sync(source)

    if accepted:
        assert _failures(emitted) == [] and fetcher.callbacks.updates
    else:
        assert _failures(emitted) == [{"op": "clone", "reason": "host_key"}]
    assert path.read_text() == contents
    clone = GitPolicyFetcher.repo_clone_path(_base(), source)
    assert not host_key_record(clone).exists()
    tofu_store = clone.parent / LIBGIT2_HOME / ".ssh" / "known_hosts"
    assert not tofu_store.exists()


@pytest.mark.fetch_backend("libgit2")
@pytest.mark.asyncio
async def test_libgit2_reads_the_known_hosts_file_as_it_is_on_each_op(
    sshd, make_origin, tmp_path, monkeypatch, emitted
):
    """The configured file reaches libgit2 through a link, read on each op.

    A file changed in place (a ConfigMap update) applies at the next op,
    and one that went away fails each SSH op as local, before libgit2
    runs.
    """
    path = tmp_path / "known_hosts"
    path.write_text(f"{_name(sshd)} {sshd.public_key('host_key')}\n")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path))
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)
    await _sync(source)
    assert _failures(emitted) == []

    path.write_text(f"{_name(sshd)} {sshd.public_key('other_host_key')}\n")
    origin.commit("master")
    await _sync(source)
    path.unlink()
    await _sync(source)

    assert _failures(emitted) == [
        {"op": "fetch", "reason": "host_key"},
        {"op": "fetch", "reason": "local"},
    ]


@pytest.mark.parametrize("cli", [True, False], ids=["cli", "libgit2"])
def test_a_known_hosts_file_that_cannot_be_read_stops_the_server_with_either_backend(
    cli, tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(tmp_path / "missing")
    )
    with pytest.raises(ValueError, match="no readable file"):
        validate_git_cli_settings()

    (tmp_path / "missing").write_text("")
    validate_git_cli_settings()


@pytest.mark.parametrize(
    "name, cli, refused",
    [
        ("with space", True, True),
        ("100%", True, True),
        ("a$b", True, True),
        ("kn'own", True, True),
        ("a:b", True, False),
        ("a:b", False, True),
        ("a$b", False, True),
        ("with space", False, False),
        ("plain", True, False),
        ("plain", False, False),
    ],
)
def test_a_base_dir_the_host_key_records_cannot_be_read_from_stops_the_server(
    name, cli, refused, tmp_path, monkeypatch
):
    """A clone's record is read by ssh as UserKnownHostsFile (whitespace, %, $,
    a quote or a backslash would make it another file); libgit2 reads its home
    as a list of directories, with $PATH expanded (: and $)."""
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path / name))
    if not refused:
        validate_git_cli_settings()
        return
    with pytest.raises(ValueError, match="BASE_DIR"):
        validate_git_cli_settings()


def test_a_base_dir_ssh_cannot_take_is_fine_with_a_known_hosts_file(
    tmp_path, monkeypatch
):
    path = tmp_path / "known_hosts"
    path.write_text("")
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(path))
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path / "with space"))
    validate_git_cli_settings()


_LIBGIT2_VERDICT = """
import sys
import pygit2

url, dest, key_file, home = sys.argv[1:]
pygit2.settings.homedir = home
seen = []


class Callbacks(pygit2.RemoteCallbacks):
    def certificate_check(self, certificate, valid, host):
        seen.append(valid)
        return True

    def credentials(self, url, username_from_url, allowed_types):
        return pygit2.KeypairFromMemory(
            username_from_url, "", open(key_file).read(), ""
        )


pygit2.clone_repository(url, dest, callbacks=Callbacks()).free()
print(seen)
"""


@pytest.mark.parametrize(
    "known, valid",
    [("its key", True), ("nothing", False), ("another key", False)],
)
def test_libgit2_valid_is_its_known_hosts_verdict(
    known, valid, sshd, make_origin, tmp_path
):
    """What GitCallback.certificate_check relies on: for an SSH host, libgit2
    passes its own check of the host's key against <its home>/.ssh/known_hosts
    as ``valid``.

    In a child interpreter: libgit2's home is process-wide.
    """
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    key = {"its key": "host_key", "another key": "other_host_key"}.get(known)
    if key is not None:
        (home / ".ssh" / "known_hosts").write_text(
            f"{_name(sshd)} {sshd.public_key(key)}\n"
        )
    origin = make_origin(tmp_path / "served" / "repo.git")
    key_file = tmp_path / "client_key"
    key_file.write_text(sshd.client_key)

    done = subprocess.run(
        [
            sys.executable,
            "-c",
            _LIBGIT2_VERDICT,
            sshd.url(origin.path),
            str(tmp_path / "clone"),
            str(key_file),
            str(home),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert done.stdout.strip() == str([valid]), done.stderr


@pytest.mark.parametrize("cli", [True, False], ids=["cli", "libgit2"])
def test_a_tls_source_gets_libgit2_s_own_certificate_verdict(cli, monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", cli)
    https = GitPolicyScopeSource(
        source_type="git",
        url="https://h.example/r.git",
        branch="master",
        auth=SSHAuthData(username="git", private_key="k"),
    )
    callback = GitCallback(https)
    assert callback.certificate_check(None, True, b"h.example") is True
    assert callback.certificate_check(None, False, b"h.example") is False


def test_the_git_command_line_trusts_on_first_use_with_the_clone_s_record(tmp_path):
    url = "ssh://git@h.example/r.git"
    source = GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="master",
        auth=SSHAuthData(username="git", private_key="k"),
    )
    remote = git_cli._remote_for_git(url, source)
    options = git_cli._ssh_host_key_options(remote, host_key_record(tmp_path / "c-0"))
    assert "StrictHostKeyChecking=accept-new" in options
    assert f"UserKnownHostsFile={tmp_path / '.c-0.known_hosts'}" in options
    assert "UpdateHostKeys=no" in options and "CheckHostIP=no" in options
    assert "GlobalKnownHostsFile=/dev/null" in options


@pytest.mark.fetch_backend("both")
@pytest.mark.asyncio
async def test_with_a_relative_base_dir_a_changed_key_is_still_refused(
    fetch_backend, sshd, make_origin, tmp_path, monkeypatch, emitted
):
    """A fetch runs git in the clone, so a record path relative to the server's
    working directory would name no file there."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", "relative-base")
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)
    await _sync(source)
    record = _record(source, fetch_backend)
    assert _key_of(record, sshd) == {sshd.public_key("host_key")}

    record.write_text(f"{_name(sshd)} {sshd.public_key('other_host_key')}\n")
    origin.commit("master")
    fetcher = await _sync(source)

    assert _failures(emitted) == [{"op": "fetch", "reason": "host_key"}]
    assert fetcher.callbacks.updates == []


@pytest.mark.fetch_backend("both")
@pytest.mark.asyncio
async def test_a_host_named_with_capitals_is_recorded_once_and_accepted(
    fetch_backend, sshd, make_origin, tmp_path, monkeypatch, emitted, log_lines
):
    """The sshd's host named ``LocalHost``.

    ssh-keyscan writes a name in lower case, as this one does, which scans
    127.0.0.1 where the sshd listens (the name may resolve to ::1 first,
    which ssh-keyscan does not fall back from).
    """
    real = shutil.which("ssh-keyscan")
    _keyscan_shim(
        tmp_path,
        monkeypatch,
        f'"{real}" -T 10 -p "$4" -t "$6" -- 127.0.0.1'
        " | sed 's/^\\[127\\.0\\.0\\.1\\]/[localhost]/'",
    )
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)
    source.url = source.url.replace("127.0.0.1", "LocalHost")

    await _sync(source)
    head = origin.commit("master")
    fetcher = await _sync(source)

    assert _failures(emitted) == []
    assert fetcher.callbacks.updates[-1][1] == head
    recorded = [m for m in log_lines("INFO") if "Recorded the SSH host key" in m]
    assert len(recorded) == 1


@pytest.mark.fetch_backend("libgit2")
@pytest.mark.asyncio
async def test_libgit2_records_a_host_after_a_line_left_without_its_newline(
    sshd, make_origin, tmp_path, emitted
):
    """A cut write, or a line deleted by hand, can leave the store without its
    last newline: the next host's lines still start lines of their own."""
    origin = make_origin(tmp_path / "served" / "repo.git")
    source = _source(sshd, origin)
    store = _record(source, "libgit2")
    store.parent.mkdir(parents=True)
    store.write_text(f"other.example {sshd.public_key('other_host_key')}")

    fetcher = await _sync(source)

    assert _failures(emitted) == [] and fetcher.callbacks.updates
    assert store.read_text().startswith(
        f"other.example {sshd.public_key('other_host_key')}\n"
    )


def _keyscan_shim(tmp_path, monkeypatch, body: str) -> Path:
    """An ssh-keyscan first on PATH that runs ``body`` (sh); the file each run
    appends its arguments to."""
    calls = tmp_path / "keyscan.calls"
    shims = tmp_path / "keyscan-bin"
    shims.mkdir()
    (shims / "ssh-keyscan").write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\n{body}\n')
    (shims / "ssh-keyscan").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    return calls


_A_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
)


def test_libgit2_records_a_capitalised_host_under_the_name_libgit2_looks_up(
    tmp_path, monkeypatch
):
    """A host recorded under the name libgit2 looks up: as the URL writes it.

    ssh-keyscan names the host in lower case. Only lines for the host asked
    for are kept.
    """
    _keyscan_shim(
        tmp_path,
        monkeypatch,
        f'echo "[gits.example]:2222 {_A_KEY}"; echo "elsewhere.example {_A_KEY}"',
    )
    clones = tmp_path / "git_sources"
    url = "ssh://git@GitS.Example:2222/r.git"

    assert prepare_libgit2_ssh(clones, url) == "[GitS.Example]:2222"
    assert prepare_libgit2_ssh(clones, url) is None

    assert libgit2_known_hosts(clones).read_text() == f"[GitS.Example]:2222 {_A_KEY}\n"


@pytest.mark.parametrize(
    "before",
    ["", "\n", "#", f"other.example {_A_KEY}\n", f"other.example {_A_KEY}"],
    ids=["empty", "a-newline", "one-character", "lines", "no-last-newline"],
)
def test_libgit2_records_a_host_on_a_line_of_its_own_after_what_is_there(
    before, tmp_path, monkeypatch
):
    """Whatever the store ends with, the host's keys start a line of their own,
    and no blank line comes before them."""
    _keyscan_shim(tmp_path, monkeypatch, f'echo "h.example {_A_KEY}"')
    clones = tmp_path / "git_sources"
    store = libgit2_known_hosts(clones)
    store.parent.mkdir(parents=True)
    store.write_text(before)

    assert prepare_libgit2_ssh(clones, "ssh://git@h.example/r.git") == "h.example"

    separator = "\n" if before and not before.endswith("\n") else ""
    assert store.read_text() == f"{before}{separator}h.example {_A_KEY}\n"


def test_an_unreadable_known_hosts_file_fails_a_libgit2_ssh_op_as_local(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", str(tmp_path / "missing")
    )

    with pytest.raises(GitCliLocalError, match="no readable file there") as failed:
        prepare_libgit2_ssh(tmp_path / "git_sources", "ssh://git@h.example/r.git")

    assert failed.value.returncode == 128


@pytest.mark.parametrize(
    "url, host_port",
    [
        ("ssh://git@h.example/r.git", ("h.example", 22)),
        ("git+ssh://h.example:2222/r.git", ("h.example", 2222)),
        ("ssh+git://git@[2001:db8::1]:2222/r.git", ("2001:db8::1", 2222)),
        ("git@h.example:org/r.git", ("h.example", 22)),
        ("h:r.git", ("h", 22)),
        ("git@[2001:db8::1]:r.git", ("2001:db8::1", 22)),
        ("https://h.example/r.git", None),
        ("ssh://git@/r.git", None),
        (":r.git", None),
        ("git@:r.git", None),
        ("./a:b", None),
        ("/srv/repos/r.git", None),
        ("git@[2001:db8::1]r.git", None),
    ],
)
def test_the_host_and_port_of_an_ssh_url(url, host_port):
    """ssh://, git+ssh://, ssh+git:// and git's scp-like form name an SSH host,
    one character long included; a local path, a URL of another scheme, or
    one with no host does not."""
    assert ssh_host_port(url) == host_port


def test_an_scp_like_host_with_capitals_is_scanned_once(tmp_path, monkeypatch):
    calls = _keyscan_shim(tmp_path, monkeypatch, f'echo "github.example {_A_KEY}"')
    clones = tmp_path / "git_sources"

    prepare_libgit2_ssh(clones, "git@GitHub.Example:org/r.git")
    prepare_libgit2_ssh(clones, "git@GitHub.Example:org/r.git")

    assert len(calls.read_text().splitlines()) == 1
    assert libgit2_known_hosts(clones).read_text() == f"GitHub.Example {_A_KEY}\n"


def test_a_keyscan_that_reads_no_key_says_why(tmp_path, monkeypatch):
    _keyscan_shim(tmp_path, monkeypatch, 'echo "connect to h.example: refused" >&2')
    with pytest.raises(pygit2.GitError, match="connect to h.example: refused"):
        prepare_libgit2_ssh(tmp_path / "git_sources", "ssh://git@h.example/r.git")


def test_a_keyscan_past_its_bound_is_a_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(git_fetcher_module, "_KEYSCAN_TIMEOUT_SECONDS", 0.5)
    _keyscan_shim(tmp_path, monkeypatch, "exec sleep 5")
    with pytest.raises(TimeoutError):
        prepare_libgit2_ssh(tmp_path / "git_sources", "ssh://git@h.example/r.git")


def test_a_host_s_keyscan_holds_up_no_other_host_and_runs_once(tmp_path, monkeypatch):
    """A keyscan of a new, slow host waits for nothing and holds up no op on
    another host; ops on that host wait for the one keyscan."""
    started = tmp_path / "slow.started"
    calls = _keyscan_shim(
        tmp_path,
        monkeypatch,
        f'case "$*" in *slow.example*) : > "{started}"; sleep 2;; esac\n'
        f'echo "$(eval echo \\${{$#}}) {_A_KEY}"',
    )
    clones = tmp_path / "git_sources"
    prepare_libgit2_ssh(clones, "ssh://git@fast.example/r.git")
    slow = [
        threading.Thread(
            target=prepare_libgit2_ssh, args=(clones, "ssh://git@slow.example/r.git")
        )
        for _ in range(2)
    ]
    for thread in slow:
        thread.start()
    deadline = time.monotonic() + 10
    while not started.exists():
        assert time.monotonic() < deadline, "the slow keyscan never started"
        time.sleep(0.02)

    began = time.monotonic()
    prepare_libgit2_ssh(clones, "ssh://git@fast.example/r.git")
    waited = time.monotonic() - began
    for thread in slow:
        thread.join(10)

    assert waited < 1.0
    scans = calls.read_text().splitlines()
    assert len([c for c in scans if c.endswith(" slow.example")]) == 1
    assert len([c for c in scans if c.endswith(" fast.example")]) == 1


@pytest.mark.asyncio
async def test_libgit2_refuses_an_ssh_connection_of_a_url_it_does_not_name_as_ssh(
    sshd, make_origin, tmp_path
):
    """Libgit2 takes a URL of an unknown scheme over SSH; GitCallback, which
    cannot name its host, gives libgit2's own verdict instead of accepting the
    key, and libgit2's home here knows no host."""
    home = tmp_path / "empty-home"
    (home / ".ssh").mkdir(parents=True)
    pygit2.settings.homedir = str(home)
    origin = make_origin(tmp_path / "served" / "repo.git")
    url = sshd.url(origin.path).replace("ssh://", "foo://")
    source = GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="master",
        auth=SSHAuthData(username="git", private_key=sshd.client_key),
    )

    with pytest.raises(pygit2.GitError, match="hostkey"):
        pygit2.clone_repository(
            url, str(tmp_path / "clone"), callbacks=GitCallback(source)
        ).free()


@pytest.mark.asyncio
async def test_only_ssh_s_own_refusal_is_a_host_key_refusal(
    git_http, make_origin, tmp_path
):
    """A server's error that reads like ssh's is a git error, not a host key
    refusal: nothing to reset."""
    make_origin(git_http.root / "repo.git")
    git_http.error = "Host key verification failed."
    url = git_http.url("repo.git")
    source = GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="master",
        auth=SSHAuthData(username="git", private_key="k"),
    )

    with pytest.raises(git_cli.GitCliError) as info:
        await git_cli.cli_clone(
            url, tmp_path / "clone", source, remote="origin", timeout=30
        )

    assert "Host key verification failed" in str(info.value)
    assert not isinstance(info.value, git_cli.GitCliHostKeyError)
