"""The E2E suite's handles on its stack: docker compose, the OPAL servers' API,
the servers' and clients' logs, and the policy repo the servers track."""

import os
import re
import secrets
import shutil
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path

import requests

APP_TESTS = Path(__file__).resolve().parent
COMPOSE_FILE = APP_TESTS / "docker-compose-app-tests.yml"
GITHUB_COMPOSE_FILE = APP_TESTS / "docker-compose-github.yml"
POLICY_FILES = APP_TESTS / "opal-tests-policy-repo-main"

# docker-compose-app-tests.yml runs two replicas of the server and two of the client.
REPLICAS = (1, 2)

# Values the compose file sets on the servers.
WEBHOOK_SECRET = "xxxxx"
JWT_AUDIENCE = "https://api.opal.ac/v1/"
JWT_ISSUER = "https://opal.ac/"
# What a data update fetches: the servers' own all-data route, so no update leaves the
# stack.
DATA_SOURCE_URL = "http://opal_server:7002/policy-data"

# Log lines the checks look for.
CLIENT_CONNECTED = "Connected to PubSub server"
CLIENT_GOT_POLICY = "Got policy bundle"
CLIENT_LOADED_STATIC_DATA = "PUT /v1/data/static -> 204"
BACKBONE_CONNECTED = "Broadcaster listener connected to channel"
BACKBONE_DROPPED = ("Broadcast subscriber ended", "Broadcaster listener error")
BACKBONE_RESYNC = "resyncing this worker's clients"
SERVER_GOT_UPDATE_REPORT = "Received update report"

# A log line with OPAL_LOG_FORMAT_INCLUDE_PID on: "<time> | <pid> | <logger> | ...",
# where the time may carry color codes.
_LOG_PID = re.compile(r"^\S+ \| (\d+) \|")


def wait_until(
    condition: Callable[[], object], timeout: float, interval: float = 1.0
) -> bool:
    """Poll ``condition`` until it returns a true value or ``timeout`` seconds
    pass.

    Returns whether it did. Exceptions from ``condition`` propagate.
    """
    deadline = time.monotonic() + timeout
    while True:
        if condition():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def run(
    command: list[str], env: dict[str, str] | None = None, cwd: Path | None = None
) -> str:
    """Run a command and return its output; raise with the output when it
    fails."""
    proc = subprocess.run(
        command,
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(command)}` failed (exit {proc.returncode}):\n"
            f"{proc.stdout}{proc.stderr}"
        )
    return proc.stdout


@dataclass(frozen=True)
class OpalAuth:
    """The stack's signing key pair and the tokens minted with it."""

    public_key: str
    # The PEM key with "_" for each newline, as OPAL_AUTH_PRIVATE_KEY takes it.
    private_key: str
    passphrase: str
    master_token: str
    client_token: str = ""
    data_source_token: str = ""

    def server_variables(self) -> dict[str, str]:
        return {
            "OPAL_AUTH_PUBLIC_KEY": self.public_key,
            "OPAL_AUTH_PRIVATE_KEY": self.private_key,
            "OPAL_AUTH_PRIVATE_KEY_PASSPHRASE": self.passphrase,
            "OPAL_AUTH_MASTER_TOKEN": self.master_token,
        }


def create_auth(home: Path, server_image: str) -> OpalAuth:
    """Generate a passphrase-protected RSA key pair and mint a client token and
    a data source token with it on a standalone server of ``server_image``."""
    key = home / "opal_crypto_key"
    passphrase = "123456"
    run(
        ["ssh-keygen", "-q", "-t", "rsa", "-b", "4096", "-m", "pem"]
        + ["-f", str(key), "-N", passphrase]
    )
    auth = OpalAuth(
        public_key=key.with_name(f"{key.name}.pub").read_text().strip(),
        private_key=key.read_text().replace("\n", "_"),
        passphrase=passphrase,
        master_token=secrets.token_hex(16),
    )
    variables = {
        **auth.server_variables(),
        "OPAL_AUTH_JWT_AUDIENCE": JWT_AUDIENCE,
        "OPAL_AUTH_JWT_ISSUER": JWT_ISSUER,
        "OPAL_REPO_WATCHER_ENABLED": "0",
    }
    name = f"opal-e2e-keygen-{secrets.token_hex(4)}"
    command = ["docker", "run", "--rm", "--detach", "--name", name]
    for variable in variables:
        command += ["--env", variable]
    run(
        [*command, "--publish", "127.0.0.1::7002", server_image],
        env={**os.environ, **variables},
    )
    try:
        published = run(["docker", "port", name, "7002"]).splitlines()[0]
        url = f"http://localhost:{published.rpartition(':')[2]}"
        assert wait_until(
            lambda: _answers(url), timeout=60
        ), f"the keygen server ({server_image}) did not answer in 60 s"
        return replace(
            auth,
            client_token=_mint_token(url, auth.master_token, "client"),
            data_source_token=_mint_token(url, auth.master_token, "datasource"),
        )
    finally:
        run(["docker", "rm", "--force", name])


def _answers(url: str) -> bool:
    try:
        return requests.get(f"{url}/", timeout=5).status_code == 200
    except requests.ConnectionError:
        return False


def _mint_token(url: str, master_token: str, token_type: str) -> str:
    response = requests.post(
        f"{url}/token",
        headers={"Authorization": f"Bearer {master_token}"},
        json={"type": token_type},
        timeout=30,
    )
    assert (
        response.ok
    ), f"POST /token ({token_type}): {response.status_code} {response.text}"
    return response.json()["token"]


class Compose:
    """``docker compose`` on the suite's compose files, with the variables they
    read."""

    def __init__(self, files: Iterable[Path], variables: dict[str, str]) -> None:
        self._files = list(files)
        self._env = {**os.environ, **variables}

    def __call__(self, *args: str, timeout: float = 600) -> str:
        """Run ``docker compose <args>`` and return its output.

        Raises:
            RuntimeError: the command failed or did not finish in ``timeout``
                seconds; the message carries its output.
        """
        proc = self._run(args, timeout)
        if proc.returncode != 0:
            raise RuntimeError(
                f"`docker compose {' '.join(args)}` failed (exit {proc.returncode}):\n"
                f"{proc.stdout}{proc.stderr}"
            )
        return proc.stdout

    def succeeds(self, *args: str, timeout: float = 60) -> bool:
        """Run ``docker compose <args>`` and return whether it exited 0."""
        return self._run(args, timeout).returncode == 0

    def _run(
        self, args: tuple[str, ...], timeout: float
    ) -> subprocess.CompletedProcess:
        command = ["docker", "compose"]
        for path in self._files:
            command += ["--file", str(path)]
        try:
            return subprocess.run(
                [*command, *args],
                env=self._env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"`docker compose {' '.join(args)}` did not finish in {timeout} s"
            ) from exc

    def logs(self, service: str, replica: int | None = None) -> str:
        """The logs of a service's replica, or of all its replicas."""
        args = ["logs", "--no-color", "--no-log-prefix"]
        if replica is not None:
            args += ["--index", str(replica)]
        return self(*args, service)

    def url(self, service: str, replica: int, port: int) -> str:
        """The host URL of a replica's published port."""
        published = self("port", "--index", str(replica), service, str(port)).strip()
        return f"http://localhost:{published.rpartition(':')[2]}"


class Fleet:
    """The running stack: two servers on a Postgres broadcast channel and two
    clients."""

    def __init__(self, compose: Compose, data_source_token: str) -> None:
        self.compose = compose
        self._data_source_token = data_source_token

    def server_url(self, replica: int = 1) -> str:
        return self.compose.url("opal_server", replica, 7002)

    def clients_missing(self, text: str) -> list[int]:
        """The client replicas whose logs do not contain ``text``."""
        return [
            replica
            for replica in REPLICAS
            if text not in self.compose.logs("opal_client", replica)
        ]

    def wait_for_each_client(self, text: str, timeout: float = 60) -> None:
        """Wait until every client has logged ``text``; fail naming the clients
        that did not."""
        missing: list[int] = []

        def everyone_logged() -> bool:
            missing[:] = self.clients_missing(text)
            return not missing

        assert wait_until(
            everyone_logged, timeout
        ), f"client(s) {missing} did not log {text!r} in {timeout} s"

    def assert_not_logged(self, service: str, text: str) -> None:
        """Fail if any replica of ``service`` logged ``text``."""
        logs = self.compose.logs(service)
        assert logs.strip(), f"no logs from {service}: nothing to check {text!r} in"
        found = [line for line in logs.splitlines() if text in line]
        assert not found, f"{service} logged {text!r}:\n" + "\n".join(found)

    def assert_not_logged_for(self, service: str, text: str, seconds: float) -> None:
        """Fail as soon as any replica of ``service`` logs ``text``, until
        ``seconds`` pass."""
        deadline = time.monotonic() + seconds
        while True:
            self.assert_not_logged(service, text)
            if time.monotonic() >= deadline:
                return
            time.sleep(1)

    def server_lines(self, text: str) -> int:
        """How many lines with ``text`` the servers logged."""
        logs = self.compose.logs("opal_server")
        return sum(text in line for line in logs.splitlines())

    def wait_for_servers(self, text: str, since: int = 0, timeout: float = 30) -> None:
        """Wait until the servers have logged more lines with ``text`` than
        ``since``."""
        assert wait_until(
            lambda: self.server_lines(text) > since, timeout
        ), f"no server logged {text!r} in {timeout} s"

    def worker_counts(self, *texts: str) -> Counter[tuple[int, int]]:
        """How many lines with any of ``texts`` each server worker logged, by
        (replica, pid)."""
        counts: Counter[tuple[int, int]] = Counter()
        for replica in REPLICAS:
            for line in self.compose.logs("opal_server", replica).splitlines():
                match = _LOG_PID.match(line)
                if match and any(text in line for text in texts):
                    counts[(replica, int(match.group(1)))] += 1
        return counts

    def wait_for_every_listener(
        self, texts: tuple[str, ...], since: Counter[tuple[int, int]], timeout: float
    ) -> None:
        """Wait until every worker that listens to the broadcast channel has
        logged one of ``texts`` more often than in ``since``."""
        listeners = set(self.worker_counts(BACKBONE_CONNECTED))
        assert listeners, f"no server worker logged {BACKBONE_CONNECTED!r}"
        behind: set[tuple[int, int]] = set()

        def all_logged() -> bool:
            now = self.worker_counts(*texts)
            behind.clear()
            behind.update(w for w in listeners if now[w] <= since[w])
            return not behind

        assert wait_until(all_logged, timeout), (
            f"server workers (replica, pid) {sorted(behind)} did not log any of "
            f"{texts} in {timeout} s"
        )

    def publish_data(self, user: str) -> None:
        """Publish a data update for ``user`` through the first server."""
        response = requests.post(
            f"{self.server_url()}/data/config",
            headers={"Authorization": f"Bearer {self._data_source_token}"},
            json={
                "entries": [
                    {
                        "url": DATA_SOURCE_URL,
                        "config": {},
                        "topics": ["policy_data"],
                        "dst_path": f"/users/{user}/location",
                        "save_method": "PUT",
                    }
                ]
            },
            timeout=30,
        )
        assert response.ok, f"POST /data/config: {response.status_code} {response.text}"

    def notify_push(self, repo_url: str) -> None:
        """Send the first server the webhook a git push of ``repo_url``
        sends."""
        response = requests.post(
            f"{self.server_url()}/webhook",
            headers={"x-webhook-token": WEBHOOK_SECRET},
            json={"gitEvent": "git.push", "repository": {"git_url": repo_url}},
            timeout=30,
        )
        assert response.ok, f"POST /webhook: {response.status_code} {response.text}"
        assert response.json()["status"] == "ok", response.text

    def statistics(self, replica: int) -> dict:
        response = requests.get(
            f"{self.server_url(replica)}/stats",
            headers={"Authorization": f"Bearer {self._data_source_token}"},
            timeout=30,
        )
        assert response.ok, f"GET /stats: {response.status_code} {response.text}"
        return response.json()

    def broadcaster_accepts_connections(self) -> bool:
        return self.compose.succeeds(
            "exec", "-T", "broadcast_channel", "pg_isready", "-U", "postgres", "-q"
        )

    def wait_for_broadcaster(self) -> None:
        assert wait_until(
            self.broadcaster_accepts_connections, timeout=30
        ), "broadcast_channel did not accept connections in 30 s"

    def wait_for_resync(self, since: Counter[tuple[int, int]]) -> None:
        """Wait until the fleet is back on the broadcast channel after a gap.

        Every listening worker resyncs its clients after a gap: it closes their
        connections and they reconnect. That is over when every worker has logged
        its resync and no client has reconnected for a few seconds, so an update
        published after this reaches a connected client.
        """
        self.wait_for_every_listener((BACKBONE_RESYNC,), since, timeout=60)
        connections = self._client_connections()
        deadline = time.monotonic() + 60
        while True:
            time.sleep(3)
            now = self._client_connections()
            if now == connections:
                return
            assert (
                time.monotonic() < deadline
            ), "clients kept reconnecting for 60 s after the resync"
            connections = now

    def _client_connections(self) -> list[int]:
        return [
            self.compose.logs("opal_client", replica).count(CLIENT_CONNECTED)
            for replica in REPLICAS
        ]


def git_environment(home: Path) -> dict[str, str]:
    """An environment in which git reads no user or system configuration and
    stores no credential."""
    config = home / "gitconfig"
    config.write_text(
        "[user]\n\tname = OPAL E2E\n\temail = e2e@opal.test\n"
        "[credential]\n\thelper =\n"
    )
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(config),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


class PolicyRepo:
    """A working copy of the policy repo on a test branch, pushed to the remote
    the servers track."""

    def __init__(
        self, server_url: str, workdir: Path, env: dict[str, str], branch: str
    ) -> None:
        self.server_url = server_url
        self.branch = branch
        self._workdir = workdir
        self._env = env

    def git(self, *args: str) -> str:
        return run(["git", *args], env=self._env, cwd=self._workdir)

    def push_policy(self, package: str) -> str:
        """Commit ``<package>.rego`` on the test branch, push it and return its
        file name."""
        name = f"{package}.rego"
        (self._workdir / name).write_text(f"package {package}\n")
        self.git("add", name)
        self.git("commit", "--quiet", "-m", f"Add {name}")
        self.git("push", "--quiet", "origin", self.branch)
        return name


def new_test_branch() -> str:
    return f"test-{secrets.token_hex(4)}"


class Gitea:
    """The stack's Gitea, as the host reaches it."""

    USER = "gitea_admin"
    PASSWORD = "admin123"
    REPO = "policy-repo"
    # The repo's URL from inside the stack, which the servers track.
    REPO_URL = f"http://gitea:3000/{USER}/{REPO}.git"

    def __init__(self, compose: Compose) -> None:
        self._compose = compose
        self.url = compose.url("gitea", 1, 3000)

    def create_admin(self) -> None:
        """Create the admin user, retrying while Gitea's database is locked."""
        command = (
            "exec",
            "-T",
            "gitea",
            "gitea",
            "admin",
            "user",
            "create",
            f"--username={self.USER}",
            f"--password={self.PASSWORD}",
            "--email=admin@gitea.local",
            "--admin",
            "--must-change-password=false",
        )
        for _ in range(10):
            try:
                self._compose(*command)
                return
            except RuntimeError as error:
                if "database is locked" not in str(error):
                    raise
            time.sleep(2)
        raise RuntimeError("could not create the Gitea admin user: database locked")

    def create_policy_repo(self, home: Path, branch: str) -> PolicyRepo:
        """Create the policy repo from ``opal-tests-policy-repo-main`` with a
        main branch and ``branch``, and return a working copy on ``branch`` in
        ``home``."""
        response = requests.post(
            f"{self.url}/api/v1/user/repos",
            auth=(self.USER, self.PASSWORD),
            json={"name": self.REPO, "private": False, "auto_init": False},
            timeout=30,
        )
        assert (
            response.status_code == 201
        ), f"creating the Gitea repo: {response.status_code} {response.text}"
        workdir = home / "repo"
        shutil.copytree(POLICY_FILES, workdir)
        port = self.url.rpartition(":")[2]
        remote = (
            f"http://{self.USER}:{self.PASSWORD}@localhost:{port}"
            f"/{self.USER}/{self.REPO}.git"
        )
        repo = PolicyRepo(self.REPO_URL, workdir, git_environment(home), branch)
        repo.git("init", "--quiet", "--initial-branch=main")
        repo.git("add", ".")
        repo.git("commit", "--quiet", "-m", "Initial policies")
        repo.git("remote", "add", "origin", remote)
        repo.git("push", "--quiet", "origin", "main")
        repo.git("checkout", "--quiet", "-b", repo.branch)
        repo.git("push", "--quiet", "--set-upstream", "origin", repo.branch)
        return repo


class GitHubPolicyRepo:
    """The policy repo on github.com, over SSH with a deploy key that can
    push."""

    URL = "git@github.com:permitio/opal-tests-policy-repo.git"

    @classmethod
    def clone(cls, deploy_key: str, home: Path, branch: str) -> PolicyRepo:
        """Clone it into ``home`` and push a new test branch from its default
        branch."""
        key = home / "deploy_key"
        key.write_text(deploy_key.strip() + "\n")
        key.chmod(0o600)
        env = {
            **git_environment(home),
            "GIT_SSH_COMMAND": f"ssh -i {key} -o IdentitiesOnly=yes",
        }
        workdir = home / "repo"
        run(["git", "clone", "--quiet", cls.URL, str(workdir)], env=env)
        repo = PolicyRepo(cls.URL, workdir, env, branch)
        repo.git("checkout", "--quiet", "-b", repo.branch)
        repo.git("push", "--quiet", "--set-upstream", "origin", repo.branch)
        return repo
