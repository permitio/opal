"""The git command-line fetch and clone (``opal_server.git_cli``) are isolated
from git configuration the libgit2 fetch never reads: the system's and the
server user's git config, hooks wherever they are configured, transports
libgit2 does not speak, and the server's own environment. Each test shows,
with a plain git given the same setup, that what it plants does take effect
when git is not isolated.

Real git against local remotes only (see git_cli_test).
"""

import base64
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pygit2
import pytest
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    NoAuthData,
)
from opal_server.config import opal_server_config
from opal_server.git_cli import GitCliError, cli_clone, cli_fetch

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

_REAL_GIT = shutil.which("git")


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLI_KILL_GRACE", 0.5)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)


def _source(url: str, auth=None) -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git",
        url=url,
        branch="master",
        auth=auth or NoAuthData(auth_type="none"),
    )


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


async def _clone(url: str, dest: Path, source=None) -> None:
    await cli_clone(url, dest, source or _source(url), remote="origin", timeout=60)


async def _fetch(clone: Path, source) -> None:
    await cli_fetch(clone, "origin", source, prune=False, timeout=60)


def _refs(path: Path) -> dict:
    repo = pygit2.Repository(str(path))
    try:
        return {
            name: str(repo.references[name].resolve().target)
            for name in repo.references
            if name.startswith("refs/remotes/") and not name.endswith("/HEAD")
        }
    finally:
        repo.free()


@pytest.fixture
def home(tmp_path, monkeypatch):
    """The server user's home, which git_cli passes to git (OpenSSH, for one,
    has no other), with an empty ``.gitconfig`` and XDG git config."""
    path = tmp_path / "home"
    (path / ".config" / "git").mkdir(parents=True)
    (path / ".gitconfig").write_text("")
    (path / ".config" / "git" / "config").write_text("")
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def system_config(tmp_path, monkeypatch):
    """A system git config that every git reads, as it reads /etc/gitconfig,
    unless told to read none (GIT_CONFIG_NOSYSTEM): a ``git`` first on PATH
    points git at it."""
    path = tmp_path / "system.gitconfig"
    path.write_text("")
    shims = tmp_path / "bin"
    shims.mkdir()
    shim = shims / "git"
    shim.write_text(
        "#!/bin/sh\n"
        f'GIT_CONFIG_SYSTEM="${{GIT_CONFIG_SYSTEM:-{path}}}" exec \'{_REAL_GIT}\' "$@"\n'
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    return path


def _plain_git(home: Path, *args: str) -> subprocess.CompletedProcess:
    """git as anyone would run it with this home and PATH, reading every
    config: the home's ``.gitconfig`` and XDG config, and a system config
    of this test (``system.gitconfig`` in the home, or system_config's),
    never this machine's own."""
    system = home.parent / "system.gitconfig"
    if not system.exists():
        system = home / "system.gitconfig"
        system.touch()
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "GIT_CONFIG_SYSTEM": str(system),
        "GIT_TERMINAL_PROMPT": "0",
    }
    return subprocess.run(
        ["git", *args], env=env, cwd=home, capture_output=True, text=True, timeout=60
    )


def _helper(marker: Path) -> str:
    """A credential helper that records each call and answers with credentials
    the source does not have."""
    return (
        f"\"!f() {{ echo $1 >> '{marker}'; "
        'test $1 = get && echo username=someone && echo password=else; }; f"'
    )


@pytest.mark.asyncio
async def test_git_reads_neither_the_system_nor_the_user_s_git_config(
    git_http, make_origin, tmp_path, home, system_config
):
    """A User-Agent, extra headers and credential helpers, in the system
    config, ``~/.gitconfig`` and ``~/.config/git/config``: a plain git sends
    and asks them all; no clone or fetch here, failing or succeeding, with a
    token or without, sends or asks any of them."""
    origin = make_origin(git_http.root / "repo.git")
    markers = {level: tmp_path / f"{level}-helper" for level in ("system", "user")}
    system_config.write_text(
        "[http]\n\tuserAgent = opal-test-system\n"
        f"[credential]\n\thelper = {_helper(markers['system'])}\n"
    )
    (home / ".gitconfig").write_text(
        "[http]\n\textraHeader = X-Opal-Test-User: read\n"
        f"[credential]\n\thelper = {_helper(markers['user'])}\n"
    )
    (home / ".config" / "git" / "config").write_text(
        "[http]\n\textraHeader = X-Opal-Test-Xdg: read\n"
    )
    url = git_http.url("repo.git")
    token = _source(url, GitHubTokenAuthData(token="the-token"))

    git_http.authorization = _basic("git", "the-token")
    control = _plain_git(home, "ls-remote", url)
    planted = git_http.requests[-1][2]
    assert control.returncode != 0
    assert planted.get("User-Agent") == "opal-test-system"
    assert planted.get("X-Opal-Test-User") == planted.get("X-Opal-Test-Xdg") == "read"
    assert markers["system"].exists() and markers["user"].exists()
    for marker in markers.values():
        marker.unlink()
    asked = len(git_http.requests)

    await _clone(url, tmp_path / "cli", token)
    origin.commit("master")
    await _fetch(tmp_path / "cli", token)
    git_http.authorization = _basic("someone", "else")
    for source in (_source(url), token):
        with pytest.raises(GitCliError):
            await _fetch(tmp_path / "cli", source)
        with pytest.raises(GitCliError):
            await _clone(url, tmp_path / "failed", source)

    assert [m for m in markers.values() if m.exists()] == []
    for _, _, headers in git_http.requests[asked:]:
        assert headers.get("User-Agent") != "opal-test-system"
        assert "X-Opal-Test-User" not in headers and "X-Opal-Test-Xdg" not in headers
        assert headers.get("Authorization") != _basic("someone", "else")


@pytest.mark.asyncio
async def test_no_credential_helper_from_the_user_s_git_config_is_ever_run(
    git_http, make_origin, tmp_path, home
):
    """Libgit2 runs no credential helper.

    One in git's config would be handed
    the source's credentials to keep (``store`` writes them to a file) on a
    success, and asked for credentials of its own on a 401.
    """
    make_origin(git_http.root / "repo.git")
    calls = tmp_path / "helper-calls"
    helper = tmp_path / "helper.sh"
    helper.write_text(f"#!/bin/sh\necho \"$@\" >> '{calls}'\ncat >> '{calls}'\n")
    helper.chmod(0o755)
    (home / ".gitconfig").write_text(f"[credential]\n\thelper = {helper}\n")
    token = f"tok{uuid.uuid4().hex}"
    url = git_http.url("repo.git")
    source = _source(url, GitHubTokenAuthData(token=token))

    git_http.authorization = _basic("git", token)
    clone = tmp_path / "cli"
    await _clone(url, clone, source)
    await _fetch(clone, source)
    git_http.authorization = _basic("someone", "else")
    with pytest.raises(GitCliError):
        await _fetch(clone, source)

    assert not calls.exists(), calls.read_text()


@pytest.mark.asyncio
async def test_no_credential_helper_from_the_clone_s_own_config_is_run(
    git_http, make_origin, tmp_path, home
):
    """The clone's own config is read, as libgit2 reads it, but a credential
    helper there is not run, on a success (it would be handed the token to
    keep) or on a 401 (it would be asked for credentials)."""
    make_origin(git_http.root / "repo.git")
    marker = tmp_path / "helper-calls"
    token = f"tok{uuid.uuid4().hex}"
    url = git_http.url("repo.git")
    source = _source(url, GitHubTokenAuthData(token=token))
    git_http.authorization = _basic("git", token)
    clone = tmp_path / "cli"
    await _clone(url, clone, source)
    repo = pygit2.Repository(str(clone))
    try:
        repo.config["credential.helper"] = _helper(marker).strip('"')
    finally:
        repo.free()
    control = _plain_git(home, "-C", str(clone), "fetch", "-q")
    assert marker.exists(), control.stderr
    marker.unlink()

    await _fetch(clone, source)
    git_http.authorization = _basic("someone", "else")
    with pytest.raises(GitCliError):
        await _fetch(clone, source)

    assert not marker.exists(), marker.read_text()


def _hook(path: Path, marker: Path) -> None:
    """A reference-transaction hook (run on every ref update a clone or fetch
    makes) that records that it ran."""
    path.mkdir(parents=True, exist_ok=True)
    hook = path / "reference-transaction"
    hook.write_text(f"#!/bin/sh\necho \"$1\" >> '{marker}'\ncat > /dev/null\n")
    hook.chmod(0o755)


@pytest.mark.parametrize(
    "where", ["user hooksPath", "user templateDir", "clone hooksPath", "clone hooks"]
)
@pytest.mark.asyncio
async def test_no_hook_runs_wherever_it_is_configured(
    where, git_origin, tmp_path, home
):
    """Libgit2 runs no hook.

    A hook from a core.hooksPath in the user's config, copied into a new
    clone from an init.templateDir, or set up in the clone itself (its
    own core.hooksPath, or its hooks directory) runs on a plain git's
    clone or fetch, and never on one here.
    """
    marker = tmp_path / "hook-ran"
    hooks = tmp_path / "hooks"
    plain, cli = tmp_path / "plain", tmp_path / "cli"
    if where == "user hooksPath":
        _hook(hooks, marker)
        (home / ".gitconfig").write_text(f"[core]\n\thooksPath = {hooks}\n")
    elif where == "user templateDir":
        _hook(tmp_path / "template" / "hooks", marker)
        (home / ".gitconfig").write_text(
            f"[init]\n\ttemplateDir = {tmp_path / 'template'}\n"
        )
    assert _plain_git(home, "clone", "-q", git_origin.url, str(plain)).returncode == 0
    await _clone(git_origin.url, cli)
    for clone in (plain, cli):
        if where == "clone hooksPath":
            _hook(hooks, marker)
            repo = pygit2.Repository(str(clone))
            try:
                repo.config["core.hooksPath"] = str(hooks)
            finally:
                repo.free()
        elif where == "clone hooks":
            _hook(clone / ".git" / "hooks", marker)
    git_origin.commit("master")
    assert _plain_git(home, "-C", str(plain), "fetch", "-q").returncode == 0
    assert marker.exists(), "the hook does not run on a plain git either"
    marker.unlink()

    new = git_origin.commit("master")
    await _fetch(cli, _source(git_origin.url))
    await _clone(git_origin.url, tmp_path / "cli2")

    assert not marker.exists(), marker.read_text()
    assert _refs(cli)["refs/remotes/origin/master"] == new
    assert not (tmp_path / "cli2" / ".git" / "hooks").exists()


@pytest.mark.asyncio
async def test_no_proxy_is_used(
    git_http, make_origin, tmp_path, home, blackhole, monkeypatch
):
    """Libgit2 (through pygit2) uses no proxy: neither the user's http.proxy
    nor the server's proxy variables reach git, which would otherwise send the
    fetch to a proxy that never answers."""
    make_origin(git_http.root / "repo.git")
    proxy = f"http://127.0.0.1:{blackhole}"
    (home / ".gitconfig").write_text(
        f"[http]\n\tproxy = {proxy}\n\tlowSpeedLimit = 1\n\tlowSpeedTime = 1\n"
    )
    url = git_http.url("repo.git")
    control = _plain_git(home, "ls-remote", url)
    assert control.returncode != 0 and git_http.requests == [], control.stderr
    for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, proxy)

    await cli_clone(url, tmp_path / "cli", _source(url), remote="origin", timeout=10)

    assert "refs/remotes/origin/master" in _refs(tmp_path / "cli")


@pytest.mark.asyncio
async def test_only_the_transports_libgit2_speaks_are_allowed(
    tmp_path, home, monkeypatch
):
    """``ext::`` runs a command of the URL's choosing, and any
    ``git-remote-<name>`` on PATH serves ``<name>://``: neither is a
    transport libgit2 has, so neither runs here."""
    marker = tmp_path / "ran"
    helpers = tmp_path / "helpers"
    helpers.mkdir()
    remote_helper = helpers / "git-remote-opaltest"
    remote_helper.write_text(f"#!/bin/sh\n: > '{marker}'\n")
    remote_helper.chmod(0o755)
    monkeypatch.setenv("PATH", f"{helpers}{os.pathsep}{os.environ['PATH']}")
    urls = [f"ext::sh -c touch% {marker}", "opaltest://somewhere/repo.git"]
    for url in urls:
        _plain_git(home, "-c", "protocol.allow=always", "ls-remote", url)
        assert marker.exists(), url
        marker.unlink()

    for url in urls:
        with pytest.raises(GitCliError) as info:
            await _clone(url, tmp_path / "cli")
        assert "not allowed" in info.value.stderr_tail

    assert not marker.exists()


@pytest.fixture
def recorded_env(tmp_path, monkeypatch):
    """A ``git`` first on PATH that records the environment it was given, then
    runs git; the file it records to."""
    shims = tmp_path / "envbin"
    shims.mkdir()
    out = tmp_path / "git-env"
    shim = shims / "git"
    shim.write_text(f"#!/bin/sh\nenv >> '{out}'\nexec '{_REAL_GIT}' \"$@\"\n")
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")

    def _read() -> dict:
        pairs = (line.split("=", 1) for line in out.read_text().splitlines())
        return dict(p for p in pairs if len(p) == 2)

    return _read


@pytest.mark.parametrize(
    "server_env, expected",
    [
        (
            {"SSL_CERT_FILE": "/certs/ca.pem", "SSL_CERT_DIR": "/certs/dir"},
            {"GIT_SSL_CAINFO": "/certs/ca.pem", "GIT_SSL_CAPATH": "/certs/dir"},
        ),
        (
            {"SSL_CERT_FILE": "/certs/ca.pem", "GIT_SSL_CAINFO": "/git/ca.pem"},
            {"GIT_SSL_CAINFO": "/git/ca.pem"},
        ),
        ({}, {}),
    ],
    ids=["openssl", "git-s-own", "none"],
)
@pytest.mark.asyncio
async def test_ca_certificates_reach_git_where_libgit2_s_openssl_finds_them(
    server_env, expected, git_origin, tmp_path, monkeypatch, recorded_env
):
    """Libgit2's OpenSSL reads SSL_CERT_FILE and SSL_CERT_DIR; git is given the
    same CA settings, unless it has its own."""
    for name in ("SSL_CERT_FILE", "SSL_CERT_DIR", "GIT_SSL_CAINFO", "GIT_SSL_CAPATH"):
        monkeypatch.delenv(name, raising=False)
    for name, value in server_env.items():
        monkeypatch.setenv(name, value)

    await _clone(git_origin.url, tmp_path / "cli")

    env = recorded_env()
    assert {k: v for k, v in env.items() if k.startswith("GIT_SSL_")} == expected
    assert "SSL_CERT_FILE" not in env and "SSL_CERT_DIR" not in env


@pytest.mark.asyncio
async def test_git_gets_none_of_the_server_s_own_environment(
    git_origin, tmp_path, monkeypatch, recorded_env
):
    """Only PATH and HOME of it, and what git_cli sets: not the server's
    secrets, an inherited GIT_DIR or GIT_WORK_TREE, nor git config passed in
    the environment."""
    for name, value in {
        "OPAL_AUTH_MASTER_TOKEN": "server-secret",
        "GIT_DIR": str(tmp_path),
        "GIT_WORK_TREE": str(tmp_path),
        "GIT_CONFIG_PARAMETERS": "'core.hookspath'='/x'",
        "GIT_TEMPLATE_DIR": str(tmp_path),
        "GIT_CONFIG_SYSTEM": str(tmp_path / "x"),
        "GIT_SSH": "/bin/false",
        "XDG_CONFIG_HOME": str(tmp_path),
    }.items():
        monkeypatch.setenv(name, value)

    await _clone(git_origin.url, tmp_path / "cli")

    env = recorded_env()
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env["GIT_ALLOW_PROTOCOL"] == "http:https:ssh:git:file"
    for name in (
        "OPAL_AUTH_MASTER_TOKEN",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_CONFIG_PARAMETERS",
        "GIT_TEMPLATE_DIR",
        "GIT_CONFIG_SYSTEM",
        "GIT_SSH",
        "XDG_CONFIG_HOME",
    ):
        assert name not in env, name


@pytest.mark.asyncio
async def test_git_does_not_inherit_git_dir_from_the_server(
    git_origin, tmp_path, monkeypatch
):
    clone = tmp_path / "cli"
    await _clone(git_origin.url, clone)
    elsewhere = tmp_path / "elsewhere.git"
    pygit2.init_repository(str(elsewhere), bare=True).free()
    monkeypatch.setenv("GIT_DIR", str(elsewhere))
    new = git_origin.commit("master")

    await _fetch(clone, _source(git_origin.url))

    assert _refs(clone)["refs/remotes/origin/master"] == new
    assert _refs(elsewhere) == {}
