"""The git command-line fetch and clone (``opal_server.git_cli``) are isolated
from what would make them act unlike the libgit2 fetch: the system's and the
server user's git config (which libgit2 does read; only their safe.directory
reaches git), ``~/.netrc``, hooks wherever they are configured, transports
libgit2 does not speak, and the server's own environment. Each test shows,
with a plain git given the same setup, that what it plants does take effect
when git is not isolated; where it says libgit2 acts the same, libgit2 is
run on the same server and setup, as the control.

Real git against local remotes only (see git_cli_test).
"""

import base64
import datetime
import os
import shutil
import ssl
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

import pygit2
import pytest
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    NoAuthData,
)
from opal_server.config import opal_server_config
from opal_server.git_cli import GitCliError, cli_clone, cli_fetch
from opal_server.git_fetcher import GitCallback

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
    """The server user's home (HOME), with an empty ``.gitconfig`` and XDG
    git config: what a plain git reads, and git_cli does not pass on."""
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


_LIBGIT2_CLONE = """
import sys

import pygit2
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    NoAuthData,
)
from opal_server.git_fetcher import GitCallback

url, dest, token, system = sys.argv[1:]
pygit2.settings.search_path[pygit2.enums.ConfigLevel.SYSTEM] = system
auth = GitHubTokenAuthData(token=token) if token else NoAuthData(auth_type="none")
source = GitPolicyScopeSource(source_type="git", url=url, branch="master", auth=auth)
try:
    pygit2.clone_repository(url, dest, callbacks=GitCallback(source)).free()
    print("cloned")
except Exception as e:
    print("failed:", repr(e))
"""


def _libgit2_clone(
    url: str,
    dest: Path,
    home: Path,
    token: str = "",
    system: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    """The control: ``url`` cloned to ``dest`` by libgit2 as the scopes
    fetcher clones (pygit2's clone_repository, with GitCallback for the
    source's token), in a child interpreter whose HOME is ``home``, plus
    ``env``: libgit2 takes its global and XDG config from HOME as it loads,
    and pygit2 its CA settings. Its system config is ``system``'s gitconfig
    (an empty directory unless given). What it printed: "cloned", or
    "failed: ..."."""
    if system is None:
        system = home.parent / "libgit2-etc"
        system.mkdir(exist_ok=True)
    child_env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
    child_env.update(HOME=str(home), **(env or {}))
    done = subprocess.run(
        [sys.executable, "-c", _LIBGIT2_CLONE, url, str(dest), token, str(system)],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return done.stdout.strip() or done.stderr.strip()


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
    and asks them all; libgit2 (the control, with the same configs) sends and
    asks none of them, and no clone or fetch here, failing or succeeding, with
    a token or without, does either."""
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
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "gitconfig").write_text(system_config.read_text())
    refused = _libgit2_clone(url, tmp_path / "libgit2-refused", home, system=etc)
    git_http.authorization = _basic("git", "the-token")
    cloned = _libgit2_clone(url, tmp_path / "libgit2", home, "the-token", etc)

    assert refused.startswith("failed"), refused
    assert cloned == "cloned", cloned
    assert [m for m in markers.values() if m.exists()] == []
    for _, _, headers in git_http.requests[asked:]:
        assert headers.get("User-Agent") != "opal-test-system"
        assert "X-Opal-Test-User" not in headers and "X-Opal-Test-Xdg" not in headers
        assert headers.get("Authorization") != _basic("someone", "else")


@pytest.mark.asyncio
async def test_no_credentials_from_the_user_s_netrc_are_sent(
    git_http, make_origin, tmp_path, home
):
    """Libcurl, which git's HTTP transport runs on, sends the credentials
    ``~/.netrc`` has for the host.

    A plain git clones with them, and libgit2 (the control, with the
    same home) does not; here, as with libgit2, a source with no auth
    gets the 401, one with a token clones with its token, and no request
    carries them.
    """
    make_origin(git_http.root / "repo.git")
    (home / ".netrc").write_text("machine 127.0.0.1 login nrcuser password nrcpass\n")
    (home / ".netrc").chmod(0o600)
    netrc = _basic("nrcuser", "nrcpass")
    url = git_http.url("repo.git")
    git_http.authorization = netrc
    control = _plain_git(home, "ls-remote", url)
    assert control.returncode == 0, control.stderr
    assert git_http.requests[-1][2].get("Authorization") == netrc
    asked = len(git_http.requests)

    libgit2_none = _libgit2_clone(url, tmp_path / "libgit2-none", home)
    with pytest.raises(GitCliError):
        await _clone(url, tmp_path / "none", _source(url))
    git_http.authorization = _basic("git", "the-token")
    libgit2_token = _libgit2_clone(url, tmp_path / "libgit2-token", home, "the-token")
    await _clone(
        url, tmp_path / "token", _source(url, GitHubTokenAuthData(token="the-token"))
    )

    assert libgit2_none.startswith("failed"), libgit2_none
    assert libgit2_token == "cloned", libgit2_token
    assert "refs/remotes/origin/master" in _refs(tmp_path / "token")
    sent = [h.get("Authorization") for _, _, h in git_http.requests[asked:]]
    assert netrc not in sent, sent


@pytest.mark.parametrize("level", ["system", "xdg", "global"])
@pytest.mark.asyncio
async def test_safe_directory_in_the_server_s_git_config_reaches_git(
    level, git_http, make_origin, tmp_path, home, monkeypatch
):
    """Libgit2 refuses a clone another user owns unless safe.directory in the
    system, XDG or global git config names it; git here reads none of those
    configs, so their safe.directory values are given to it with the op's own
    config.

    A fetch of a clone git takes for another user's
    (GIT_TEST_ASSUME_DIFFERENT_OWNER) fails until one of them names the
    clone, and then fetches.
    """
    origin = make_origin(git_http.root / "repo.git")
    url = git_http.url("repo.git")
    clone = tmp_path / "cli"
    await _clone(url, clone)
    shims = tmp_path / "ownerbin"
    shims.mkdir()
    (shims / "git").write_text(
        "#!/bin/sh\n"
        'case " $* " in *" fetch "*) '
        "GIT_TEST_ASSUME_DIFFERENT_OWNER=1; export GIT_TEST_ASSUME_DIFFERENT_OWNER;; "
        "esac\n"
        f"exec '{_REAL_GIT}' \"$@\"\n"
    )
    (shims / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    levels = pygit2.enums.ConfigLevel
    configs = {
        "system": (levels.SYSTEM, tmp_path / "etc", "gitconfig"),
        "xdg": (levels.XDG, home / ".config" / "git", "config"),
        "global": (levels.GLOBAL, home, ".gitconfig"),
    }
    search_path = pygit2.settings.search_path
    before = {at: search_path[at] for at, _, _ in configs.values()}
    try:
        for at, directory, _ in configs.values():
            search_path[at] = str(directory)
        with pytest.raises(GitCliError, match="dubious ownership"):
            await _fetch(clone, _source(url))
        _, directory, name = configs[level]
        directory.mkdir(exist_ok=True)
        (directory / name).write_text(f"[safe]\n\tdirectory = {clone.resolve()}\n")
        new = origin.commit("master")
        await _fetch(clone, _source(url))
    finally:
        for at, path in before.items():
            search_path[at] = path

    assert _refs(clone)["refs/remotes/origin/master"] == new


@pytest.mark.asyncio
async def test_no_credential_helper_from_the_user_s_git_config_is_ever_run(
    git_http, make_origin, tmp_path, home
):
    """A credential helper in git's config would be handed the source's
    credentials to keep (``store`` writes them to a file) on a success, and
    asked for credentials of its own on a 401.

    libgit2 (the control, with the same home) runs it on neither, and
    neither does git here.
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
    control = _plain_git(home, "ls-remote", url)
    assert calls.exists(), control.stderr
    calls.unlink()

    libgit2_cloned = _libgit2_clone(url, tmp_path / "libgit2", home, token)
    clone = tmp_path / "cli"
    await _clone(url, clone, source)
    await _fetch(clone, source)
    git_http.authorization = _basic("someone", "else")
    libgit2_refused = _libgit2_clone(url, tmp_path / "libgit2-refused", home, token)
    with pytest.raises(GitCliError):
        await _fetch(clone, source)

    assert libgit2_cloned == "cloned", libgit2_cloned
    assert libgit2_refused.startswith("failed"), libgit2_refused
    assert not calls.exists(), calls.read_text()


@pytest.mark.asyncio
async def test_no_credential_helper_from_the_clone_s_own_config_is_run(
    git_http, make_origin, tmp_path, home
):
    """The clone's own config is read, as libgit2 reads it, but a credential
    helper there is not run, on a success (it would be handed the token to
    keep) or on a 401 (it would be asked for credentials): a plain git runs it,
    and libgit2 (the control, fetching the same clone) does not."""
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

    libgit2 = pygit2.Repository(str(clone))
    try:
        libgit2.remotes["origin"].fetch(callbacks=GitCallback(source))
        git_http.authorization = _basic("someone", "else")
        with pytest.raises(pygit2.GitError):
            libgit2.remotes["origin"].fetch(callbacks=GitCallback(source))
    finally:
        libgit2.free()
    assert not marker.exists(), marker.read_text()
    git_http.authorization = _basic("git", token)
    await _fetch(clone, source)
    git_http.authorization = _basic("someone", "else")
    with pytest.raises(GitCliError):
        await _fetch(clone, source)

    assert not marker.exists(), marker.read_text()


@pytest.mark.asyncio
async def test_git_asks_no_askpass_program_and_no_terminal_for_credentials(
    git_http, make_origin, tmp_path, home
):
    """A server that asks for credentials the source does not have: a plain git
    asks the askpass program the clone's own config names (core.askPass); here
    git asks neither it nor a terminal, and fails, saying so."""
    make_origin(git_http.root / "repo.git")
    url = git_http.url("repo.git")
    clone = tmp_path / "cli"
    await _clone(url, clone)
    marker = tmp_path / "askpass-ran"
    askpass = tmp_path / "askpass.sh"
    askpass.write_text(f"#!/bin/sh\necho \"$1\" >> '{marker}'\necho someone\n")
    askpass.chmod(0o755)
    repo = pygit2.Repository(str(clone))
    try:
        repo.config["core.askPass"] = str(askpass)
    finally:
        repo.free()
    git_http.authorization = _basic("someone", "else")
    control = _plain_git(home, "-C", str(clone), "fetch", "-q")
    assert marker.exists(), control.stderr
    marker.unlink()

    with pytest.raises(GitCliError) as info:
        await _fetch(clone, _source(url))

    assert not marker.exists(), marker.read_text()
    assert "terminal prompts disabled" in info.value.stderr_tail


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
    """libgit2 (the control, with the same home and variables) uses no proxy,
    and neither does git here: neither the user's http.proxy nor the server's
    proxy variables reach git, which would otherwise send the fetch to a proxy
    that never answers."""
    make_origin(git_http.root / "repo.git")
    proxy = f"http://127.0.0.1:{blackhole}"
    (home / ".gitconfig").write_text(
        f"[http]\n\tproxy = {proxy}\n\tlowSpeedLimit = 1\n\tlowSpeedTime = 1\n"
    )
    url = git_http.url("repo.git")
    control = _plain_git(home, "ls-remote", url)
    assert control.returncode != 0 and git_http.requests == [], control.stderr
    proxies = {
        name: proxy
        for name in (
            "http_proxy",
            "HTTP_PROXY",
            "https_proxy",
            "HTTPS_PROXY",
            "ALL_PROXY",
        )
    }
    libgit2 = _libgit2_clone(url, tmp_path / "libgit2", home, env=proxies)
    assert libgit2 == "cloned", libgit2
    for name, value in proxies.items():
        monkeypatch.setenv(name, value)

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


def _ca_signed_localhost(tmp_path: Path) -> Tuple[Path, ssl.SSLContext]:
    """A CA made for the test, valid for a day, and a server context that
    presents a certificate it signed for localhost: the CA's PEM file, and the
    context.

    A DNS name, as libgit2 refuses a self-signed certificate for an IP
    address (conftest's tls_cert) that git takes.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OPAL test CA")])
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])

    def _signed_by_the_ca(subject, public_key, extension, critical):
        return (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_name)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(extension, critical=critical)
            .sign(ca_key, hashes.SHA256())
        )

    ca = _signed_by_the_ca(
        ca_name,
        ca_key.public_key(),
        x509.BasicConstraints(ca=True, path_length=None),
        True,
    )
    leaf = _signed_by_the_ca(
        leaf_name,
        key.public_key(),
        x509.SubjectAlternativeName([x509.DNSName("localhost")]),
        False,
    )
    pem = serialization.Encoding.PEM
    ca_path, leaf_path, key_path = (
        tmp_path / n for n in ("ca.pem", "leaf.pem", "leaf.key")
    )
    ca_path.write_bytes(ca.public_bytes(pem))
    leaf_path.write_bytes(leaf.public_bytes(pem))
    key_path.write_bytes(
        key.private_bytes(
            pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(leaf_path, key_path)
    return ca_path, context


@pytest.mark.parametrize("where", ["SSL_CERT_FILE", "SSL_CERT_DIR", "neither"])
@pytest.mark.asyncio
async def test_an_https_server_is_trusted_where_libgit2_trusts_it(
    where, git_http, make_origin, tmp_path, home, monkeypatch
):
    """An https server whose certificate a CA of its own signed: libgit2 (the
    control, with the same variables) trusts it when SSL_CERT_FILE or
    SSL_CERT_DIR names that CA, and not otherwise, and so does git here."""
    make_origin(git_http.root / "repo.git")
    ca, git_http.tls = _ca_signed_localhost(tmp_path)
    url = f"https://localhost:{git_http.server_address[1]}/repo.git"
    for name in ("SSL_CERT_FILE", "SSL_CERT_DIR", "GIT_SSL_CAINFO", "GIT_SSL_CAPATH"):
        monkeypatch.delenv(name, raising=False)
    env = {}
    if where == "SSL_CERT_FILE":
        env[where] = str(ca)
    elif where == "SSL_CERT_DIR":
        directory = tmp_path / "cas"
        directory.mkdir()
        shutil.copy(ca, directory / "ca.pem")
        openssl = shutil.which("openssl")
        hashed = openssl and subprocess.run(
            [openssl, "rehash", str(directory)], capture_output=True, check=False
        )
        if not hashed or hashed.returncode != 0:
            pytest.skip("no openssl rehash to name a CA directory's files by hash")
        env[where] = str(directory)

    libgit2 = _libgit2_clone(url, tmp_path / "libgit2", home, env=env)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    if where == "neither":
        with pytest.raises(GitCliError):
            await _clone(url, tmp_path / "cli")
        assert libgit2.startswith("failed"), libgit2
    else:
        await _clone(url, tmp_path / "cli")
        assert libgit2 == "cloned", libgit2
        assert "refs/remotes/origin/master" in _refs(tmp_path / "cli")


@pytest.mark.asyncio
async def test_git_gets_none_of_the_server_s_own_environment(
    git_origin, tmp_path, monkeypatch, recorded_env
):
    """Only PATH of it, and what git_cli sets (HOME is /dev/null): not the
    server's secrets, its HOME, an inherited GIT_DIR or GIT_WORK_TREE, nor git
    config passed in the environment."""
    for name, value in {
        "HOME": str(tmp_path / "home"),
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
    assert env["HOME"] == os.devnull
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
