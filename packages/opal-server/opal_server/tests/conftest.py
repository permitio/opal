"""Fixtures shared by the opal-server tests."""

import gzip
import os
import selectors
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import opal_server.scopes.task as task_module
import pygit2
import pytest
from opal_server.config import opal_server_config


class NoScopes:
    """A ScopeRepository with no scopes."""

    def __init__(self, db):
        pass

    async def all(self):
        return []


@pytest.fixture
def preload_sandbox(monkeypatch, tmp_path):
    """For tests that run ScopesPolicyWatcherTask.preload_scopes: no scopes,
    and a BASE_DIR under tmp_path.

    The preload runs the hung-clone sweep on BASE_DIR before its sync,
    so without this the sweep would remove markers, or with
    SCOPES_GIT_RECLONE_HUNG_ON_START set in the environment delete
    clones, in the default BASE_DIR of whoever runs the tests.
    """
    monkeypatch.setattr(task_module, "ScopeRepository", NoScopes)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))


# --- local git remotes, for the git command-line fetch tests -------------------

_SIG = pygit2.Signature("opal-test", "opal-test@example.com")


class GitOrigin:
    """A bare repository on local disk, written with pygit2 (so no git config
    of whoever runs the tests is involved)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.repo = pygit2.init_repository(str(path), bare=True)

    @property
    def url(self) -> str:
        return f"file://{self.path}"

    def commit(self, branch: str = "master", files: Optional[Dict] = None) -> str:
        """Commit ``files`` (name -> str or bytes) on top of ``branch``."""
        ref = f"refs/heads/{branch}"
        parent = self.repo.references.get(ref)
        parents = [parent.target] if parent is not None else []
        if parent is not None:
            head = self.repo[parent.target]
            assert isinstance(head, pygit2.Commit), head
            builder = self.repo.TreeBuilder(head.tree)
        else:
            builder = self.repo.TreeBuilder()
        files = files or {"policy.rego": f"package p\n# {time.time_ns()}\n"}
        for name, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            builder.insert(
                name, self.repo.create_blob(data), pygit2.enums.FileMode.BLOB
            )
        oid = self.repo.create_commit(
            ref, _SIG, _SIG, f"commit on {branch}", builder.write(), parents
        )
        return str(oid)

    def branch(self, name: str, from_branch: str = "master") -> None:
        target = self.repo.references[f"refs/heads/{from_branch}"].target
        self.repo.references.create(f"refs/heads/{name}", target)

    def delete(self, branch: str) -> None:
        self.repo.references.delete(f"refs/heads/{branch}")


@pytest.fixture
def make_origin():
    """A factory of GitOrigin: an origin at a path, with ``master`` and the
    branches ``dev`` and ``feature/x``."""
    made = []

    def _make(path: Path) -> GitOrigin:
        origin = GitOrigin(path)
        origin.commit("master", {"policy.rego": "package p\n", "data.json": "{}"})
        origin.branch("dev")
        origin.commit("dev", {"dev.rego": "package dev\n"})
        origin.branch("feature/x")
        made.append(origin)
        return origin

    yield _make
    for origin in made:
        origin.repo.free()


@pytest.fixture
def git_origin(tmp_path, make_origin) -> GitOrigin:
    """An origin in ``tmp_path / "origin.git"`` (see make_origin)."""
    return make_origin(tmp_path / "origin.git")


class _Holder:
    """A TCP listener on localhost that takes connections and never answers:
    a black-holed remote. A connection is closed once its client has
    closed it, so that this side holds no descriptor for a client that is
    gone."""

    def __init__(self) -> None:
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(64)
        self._sock.setblocking(False)
        self.port = self._sock.getsockname()[1]
        self._selector = selectors.DefaultSelector()
        self._selector.register(self._sock, selectors.EVENT_READ)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            for key, _ in self._selector.select(timeout=0.1):
                if key.fileobj is self._sock:
                    try:
                        conn, _ = self._sock.accept()
                    except OSError:
                        continue
                    conn.setblocking(False)
                    self._selector.register(conn, selectors.EVENT_READ)
                    continue
                conn = cast(socket.socket, key.fileobj)
                try:
                    data = conn.recv(65536)
                except OSError:
                    data = b""
                if not data:
                    self._selector.unregister(conn)
                    conn.close()
        for key in list(self._selector.get_map().values()):
            cast(socket.socket, key.fileobj).close()
        self._selector.close()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(5)


@pytest.fixture
def blackhole():
    """The port of a local TCP endpoint that accepts and never answers."""
    holder = _Holder()
    yield holder.port
    holder.close()


class _Dripper:
    """A local HTTP endpoint that answers every request with a 200 whose body
    never ends: one more line every 50 ms. The transfer keeps making
    progress, so nothing short of a hard timeout stops a client."""

    def __init__(self) -> None:
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(64)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self.bytes_sent = 0
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        self._sock.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                continue
            threading.Thread(target=self._drip, args=(conn,), daemon=True).start()

    def _drip(self, conn: socket.socket) -> None:
        try:
            conn.recv(65536)
            conn.sendall(
                b"HTTP/1.0 200 OK\r\n"
                b"Content-Type: application/x-git-upload-pack-advertisement\r\n"
                b"\r\n001e# service=git-upload-pack\n0000"
            )
            i = 0
            while not self._stop.wait(0.05):
                line = f"{i:040x} refs/heads/drip-{i}\n".encode()
                conn.sendall(f"{len(line) + 4:04x}".encode() + line)
                self.bytes_sent += len(line) + 4
                i += 1
        except OSError:
            pass
        finally:
            conn.close()

    def close(self) -> None:
        self._stop.set()
        self._sock.close()


@pytest.fixture
def dripper():
    """A local HTTP endpoint whose answer drips in forever."""
    server = _Dripper()
    yield server
    server.close()


class GitHttpServer(ThreadingHTTPServer):
    """``git http-backend`` over HTTP on localhost, for the repositories under
    ``root``.

    ``redirect_to``: a base URL every request is redirected to (302), path
    and query kept, before anything else. ``authorization``: the exact
    Authorization header every request must carry, else 401.
    ``stall_after``: send only this many bytes of a pack (the answer to a
    fetch request), then hold the connection open until the server closes.
    ``error``: answer every request (once authorized) with a git ``ERR``
    packet carrying this message, which git prints as a remote error.
    Every request's headers are kept in ``requests``.
    """

    daemon_threads = True

    def __init__(self, root: Path) -> None:
        super().__init__(("127.0.0.1", 0), _GitHttpHandler)
        self.root = root
        self.redirect_to: Optional[str] = None
        self.authorization: Optional[str] = None
        self.stall_after: Optional[int] = None
        self.error: Optional[str] = None
        self.stalled = threading.Event()
        self.release = threading.Event()
        self.requests: List[Tuple[str, str, Dict[str, str]]] = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def url(self, name: str, userinfo: str = "") -> str:
        prefix = f"{userinfo}@" if userinfo else ""
        return f"http://{prefix}127.0.0.1:{self.server_address[1]}/{name}"

    def close(self) -> None:
        self.release.set()
        self.shutdown()
        self.server_close()


def _git() -> str:
    """The git on PATH."""
    git = shutil.which("git")
    assert git is not None, "these tests need git on PATH"
    return git


def _pkt_line(data: bytes) -> bytes:
    """``data`` as a git pkt-line: its length, header included, in 4 hex
    digits, then the data."""
    return b"%04x" % (len(data) + 4) + data


class _GitHttpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        self._serve()

    def do_POST(self) -> None:
        self._serve()

    def _serve(self) -> None:
        server = cast(GitHttpServer, self.server)
        server.requests.append((self.command, self.path, dict(self.headers)))
        if server.redirect_to is not None:
            self.send_response(302)
            self.send_header("Location", server.redirect_to.rstrip("/") + self.path)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if (
            server.authorization is not None
            and self.headers.get("Authorization") != server.authorization
        ):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="git"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if server.error is not None:
            body = (
                _pkt_line(b"# service=git-upload-pack\n")
                + b"0000"
                + _pkt_line(f"ERR {server.error}".encode())
            )
            self.send_response(200)
            self.send_header(
                "Content-Type", "application/x-git-upload-pack-advertisement"
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        path, _, query = self.path.partition("?")
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        env = {
            "PATH": os.environ["PATH"],
            "HOME": os.environ.get("HOME", "/"),
            "GIT_PROJECT_ROOT": str(server.root),
            "GIT_HTTP_EXPORT_ALL": "1",
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "REQUEST_METHOD": self.command,
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(len(body)),
            "REMOTE_ADDR": "127.0.0.1",
        }
        if self.headers.get("Git-Protocol"):
            env["GIT_PROTOCOL"] = self.headers["Git-Protocol"]
        plain = body
        if self.headers.get("Content-Encoding"):
            env["HTTP_CONTENT_ENCODING"] = self.headers["Content-Encoding"]
            plain = gzip.decompress(body)
        out = subprocess.run(
            [_git(), "http-backend"],
            input=body,
            env=env,
            capture_output=True,
            check=False,
        ).stdout
        head, _, payload = out.partition(b"\r\n\r\n")
        status, headers = 200, []
        for line in head.decode("latin-1").split("\r\n"):
            key, _, value = line.partition(":")
            if key.lower() == "status":
                status = int(value.split()[0])
            elif key:
                headers.append((key, value.strip()))
        stall = (
            server.stall_after
            if self.command == "POST"
            and (b"command=fetch" in plain or b"want " in plain)
            else None
        )
        self.send_response(status)
        for key, value in headers:
            self.send_header(key, value)
        if stall is None:
            self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if stall is None:
            self.wfile.write(payload)
            return
        self.wfile.write(payload[:stall])
        self.wfile.flush()
        server.stalled.set()
        server.release.wait()


@pytest.fixture
def make_git_http():
    """A factory of GitHttpServer: a git HTTP server on a port of its own, for
    the repositories in a directory (created)."""
    servers = []

    def _make(root: Path) -> GitHttpServer:
        root.mkdir(parents=True, exist_ok=True)
        servers.append(GitHttpServer(root))
        return servers[-1]

    yield _make
    for server in servers:
        server.close()


@pytest.fixture
def git_http(tmp_path, make_git_http):
    """A git HTTP server for the repositories in ``tmp_path / "served"``."""
    return make_git_http(tmp_path / "served")


def all_processes() -> List[Tuple[int, int, int, str]]:
    """(pid, parent pid, process group, command line) of every process: from
    /proc where there is one, else from ps."""
    if os.path.isdir("/proc/self"):
        return _proc_processes()
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid=,pgid=,args="],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    found = []
    for line in out.splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4:
            found.append((int(fields[0]), int(fields[1]), int(fields[2]), fields[3]))
    return found


def _proc_processes() -> List[Tuple[int, int, int, str]]:
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as f:
                stat_fields = f.read().rpartition(")")[2].split()
            with open(f"/proc/{name}/cmdline", "rb") as f:
                args = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            continue  # gone meanwhile
        found.append((int(name), int(stat_fields[1]), int(stat_fields[2]), args))
    return found


def _processes_with(marker: str) -> List[Tuple[int, int, str]]:
    return [(p, g, a) for p, _, g, a in all_processes() if marker in a]


@pytest.fixture
def processes_with():
    """A function: (pid, process group, command line) of every process whose
    command line holds ``marker``."""
    return _processes_with


@pytest.fixture
def git_groups(monkeypatch):
    """Every group git_cli makes, as it makes it.

    A group is there once its op's start is over: a test that stops an
    op with a cancel waits for one, as a cancel during the start is a
    stop of another kind (asyncio kills sh, and the watchdog the rest:
    no SIGTERM, no grace).
    """
    from opal_server import git_cli

    made = []

    class _Recorded(git_cli._Group):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(git_cli, "_Group", _Recorded)
    return made


@pytest.fixture
def process_table():
    """all_processes, as a fixture."""
    return all_processes


class Sshd:
    """An OpenSSH server on localhost, run as this user, that serves git
    through git-shell to a client with a key.

    It has a host key of its own, which no known_hosts file names.
    """

    def __init__(self, base: Path) -> None:
        sshd = shutil.which("sshd") or "/usr/sbin/sshd"
        if not os.path.exists(sshd):
            pytest.skip("no sshd on this machine")
        git = _git()
        exec_path = subprocess.run(
            [git, "--exec-path"], capture_output=True, text=True, check=True
        ).stdout.strip()
        base.mkdir(parents=True, exist_ok=True)
        self.base = base
        for name in ("host_key", "other_host_key", "client_key"):
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(base / name)],
                check=True,
                capture_output=True,
            )
        authorized = base / "authorized_keys"
        authorized.write_text((base / "client_key.pub").read_text())
        authorized.chmod(0o600)
        shell = base / "git-shell.sh"
        shell.write_text(
            "#!/bin/sh\n"
            f"PATH={os.path.dirname(git)}:/usr/bin:/bin; export PATH\n"
            f'exec {exec_path}/git-shell -c "$SSH_ORIGINAL_COMMAND"\n'
        )
        shell.chmod(0o755)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        config = base / "sshd_config"
        config.write_text(
            f"Port {self.port}\nListenAddress 127.0.0.1\n"
            f"HostKey {base / 'host_key'}\nPidFile {base / 'sshd.pid'}\n"
            f"AuthorizedKeysFile {authorized}\nUsePAM no\nStrictModes no\n"
            "PasswordAuthentication no\nKbdInteractiveAuthentication no\n"
            f"PubkeyAuthentication yes\nForceCommand {shell}\n"
        )
        self._proc = subprocess.Popen(
            [sshd, "-D", "-e", "-f", str(config)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 10
        while True:
            if self._proc.poll() is not None:
                assert self._proc.stderr is not None
                err = self._proc.stderr.read().decode(errors="replace")
                pytest.skip(f"sshd did not start: {err.strip()[-300:]}")
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close()
                break
            except OSError:
                if time.monotonic() > deadline:
                    self.close()
                    pytest.skip("sshd did not start listening")
                time.sleep(0.05)

    def url(self, repo: Path) -> str:
        user = subprocess.run(
            ["id", "-un"], capture_output=True, text=True, check=True
        ).stdout.strip()
        return f"ssh://{user}@127.0.0.1:{self.port}{repo}"

    @property
    def client_key(self) -> str:
        return (self.base / "client_key").read_text()

    def public_key(self, name: str) -> str:
        return " ".join((self.base / f"{name}.pub").read_text().split()[:2])

    def close(self) -> None:
        self._proc.terminate()
        try:
            self._proc.wait(5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()


@pytest.fixture
def sshd(tmp_path):
    """A local sshd serving git, or a skip where none can be started."""
    server = Sshd(tmp_path / "sshd")
    yield server
    server.close()
