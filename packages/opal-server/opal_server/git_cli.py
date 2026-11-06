"""Scope fetches and clones through the git command line (PER-17993).

With SCOPES_GIT_FETCH_WITH_CLI on, the scopes fetcher runs ``git fetch`` and
``git clone`` as child processes instead of calling libgit2 on a thread. A
libgit2 call cannot be stopped once it hangs: its thread runs until the remote
answers or the process ends, and the clone is not synced meanwhile. A child
process can be stopped. Each op runs in a process group of its own; at its
timeout the group gets SIGTERM, then SIGKILL, and the op is over only once the
group is gone and what it left in the clone has been cleaned up.

Each op holds an flock on its clone (a lock file beside it), which git's whole
group inherits: while any process of an op is alive, in this process or in
one whose worker died, no other op, repack or cleanup touches that clone.
The group also ends itself when the process that started it dies: sh's stdin
is a pipe from this process, and a watchdog in the group kills it when that
pipe closes.

A clone made here has what the scopes fetcher reads from a libgit2 clone:
the same remote and URL, the same ``refs/remotes/<remote>/*`` and a
FETCH_HEAD, which, as with libgit2, only a fetch that succeeded rewrites. So
the fetcher reads it with pygit2 as before, and the setting can be switched
either way over existing clones.

git reads neither the system's nor the user's git config, which would bring
hooks, credential helpers, headers and proxies to every op, and is given only
their safe.directory. libgit2 does read them (a url.insteadOf there, say), so
whatever else they set is lost when the setting goes on. git runs no hooks,
reads no ~/.netrc and speaks only http(s), ssh, git and file. Credentials
never reach a command line. git hands the URL it fetches from to its remote
helper (git-remote-https) as an argument, so git is given the remote's URL
without the user and password in it, and, for a fetch, the refspecs to fetch
instead of the remote's name. The user and password go in through git's
environment, to a credential helper configured there (GIT_CONFIG_COUNT) that
answers only for the source's own host, as libgit2's credentials callback is
asked per host; an SSH key goes in a file only this user can read, in a
directory of its own, removed when the op ends.
"""

import asyncio
import base64
import fcntl
import math
import os
import pwd
import re
import secrets
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

import pygit2
from opal_common.http_utils import redact_sensitive_text
from opal_common.logger import logger
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    SSHAuthData,
)
from opal_server.config import opal_server_config


class GitCliError(RuntimeError):
    """A git fetch or clone failed.

    ``returncode`` is git's exit status (128 for its fatal errors, 128 plus
    the signal for a git killed by one), or -1 when git's status never came
    back (the sh it ran under was killed first). ``stderr_tail`` is the end
    of what git wrote to stderr, credentials redacted.
    """

    def __init__(self, returncode: int, stderr_tail: str) -> None:
        message = f"git exited with status {returncode}"
        super().__init__(f"{message}: {stderr_tail}" if stderr_tail else message)
        self.returncode = returncode
        self.stderr_tail = stderr_tail


class GitCliLocalError(GitCliError):
    """An op failed on this machine, before or around git, saying nothing
    about the remote: no git on PATH (127), git could not be started (127),
    the clone or its remote is not there, its directory cannot be set up or
    put in place, SCOPES_GIT_SSH_KNOWN_HOSTS cannot be read, or the URL is
    one git cannot be given safely (128)."""


class GitCliBusyError(GitCliLocalError):
    """Another op holds the clone's lock: a git op of another process, or one
    whose process died and whose git has not exited yet.

    Nothing was done; the clone is left to that op.
    """


class GitCliRefusedSourceError(GitCliLocalError):
    """The source's URL or credentials cannot be given to git without a
    credential on its command line or in what it prints (a URL that does not
    parse, a password in an scp-like URL, a credential in the query string, a
    newline in a user or password).

    Nothing ran; only a change of the source makes it work.
    """


class GitCliTimeoutError(TimeoutError):
    """A git fetch or clone ran past its timeout and was stopped."""


# How long OPAL waits for the group to be reaped after SIGKILL. Only a process
# in uninterruptible I/O outlives it, so an op returns at most the kill grace
# plus this past its timeout (its on_gone can come later, once that process
# exits).
KILL_WAIT_SECONDS = 10.0
_DEFAULT_KILL_GRACE_SECONDS = 5.0
# How often a group whose pipes are closed is checked for members left, and a
# clone's lock for being free.
_GROUP_POLL_SECONDS = 0.05
_LOCK_POLL_SECONDS = 1.0
_STDERR_TAIL_CHARS = 2000
# GIT_CONFIG_GLOBAL needs 2.32.
MIN_GIT_VERSION = (2, 32)
# The only variables git inherits, as for the repack: OPAL's own secrets have no
# business in git's environment, and an inherited GIT_DIR or GIT_WORK_TREE
# would point git at some other repository. Proxy variables are dropped, as
# libgit2 (through pygit2) uses no proxy. HOME is not passed on (see
# _isolated_env). nss_wrapper's variables (LD_PRELOAD, which the server
# process has already loaded, and NSS_WRAPPER_*) are passed on: they give a
# uid with no passwd entry the user that ssh looks up before anything else.
_ENV_ALLOWLIST = ("PATH", "GIT_SSL_CAINFO", "GIT_SSL_CAPATH", "LD_PRELOAD")
_ENV_ALLOWED_PREFIX = "NSS_WRAPPER_"
# Where OpenSSL, which libgit2 uses, looks for CA certificates, and where git's
# own TLS library is told to.
_CA_ENV = (("SSL_CERT_FILE", "GIT_SSL_CAINFO"), ("SSL_CERT_DIR", "GIT_SSL_CAPATH"))
# What libgit2 speaks, and file:// for local clones: no ext:: and no other
# git-remote-* helper.
_ALLOWED_PROTOCOLS = "http:https:ssh:git:file"
_SH = "/bin/sh"
# git runs under sh, which prints git's exit status on its stdout once git is
# done. The status is read from there because waitpid cannot be trusted for it:
# the scope preload runs in the gunicorn master, whose SIGCHLD handler reaps
# every child with waitpid(-1), and asyncio then reports 255 for a child that
# handler reaped first. Python 3.12's PidfdChildWatcher loses that race on
# every child (it reaps through a pidfd the handler's waitpid(-1) beats);
# 3.11's ThreadedChildWatcher only when the handler happens to run first.
# git's own stdout goes to /dev/null, so the status is all that sh's stdout
# carries, and no status at all means sh was killed before git's came back.
#
# sh's stdin is a pipe from this process that nothing writes to. A watchdog in
# sh's group reads it (on fd 3, as an asynchronous list's stdin is /dev/null)
# and SIGKILLs the whole group at its end of file: when this process dies, or
# closes the pipe. sh closes fd 3 before git starts, and SIGKILLs the watchdog
# once git is done, and reaps it: left to pid 1 (sh's orphan once sh exits) it
# would be a zombie in the group for as long as pid 1 takes, or for good under
# a pid 1 that reaps nothing; wait's 2>/dev/null keeps the shell's "Killed"
# out of git's stderr. The SIGTERM of a stop ends neither: the watchdog ignores
# it, so a process that dies during the kill grace still takes git with it,
# and sh traps it (a handler, which git does not inherit as it would an
# ignored signal), so sh waits for git and reports its status, and is reaped
# only once git is done.
#
# WATCHDOG_SCRIPT is that start, shared with the repack (git_fetcher), whose sh
# exits with git's status instead: $w is the watchdog's pid, for sh to SIGKILL
# and reap once its command is done.
WATCHDOG_SCRIPT = (
    "exec 3<&0 </dev/null; "
    "{ trap '' TERM; read -r _ <&3; kill -KILL 0; } >/dev/null 2>&1 & w=$!; "
    "exec 3<&-; trap : TERM; "
)
_STATUS_SCRIPT = WATCHDOG_SCRIPT + (
    '"$@" >/dev/null; s=$?; kill -KILL "$w" 2>/dev/null; wait "$w" 2>/dev/null; '
    'echo "$s"'
)
# fetch.unpackLimit=1 keeps every fetched object in a pack, as libgit2 does,
# rather than spreading a small fetch over loose objects that the repack
# trigger (a pack count) does not see. The advice would only fill the stderr
# that errors quote. protocol.version=2, git's default, pinned: a clone's own
# config, which git reads, could set another.
_GIT_CONFIG_ARGS = (
    "-c",
    "fetch.unpackLimit=1",
    "-c",
    "advice.fetchShowForcedUpdates=false",
    "-c",
    "protocol.version=2",
)
# The credential helper, in git's environment config. It answers git's "get"
# with the op's user and password only when git asks for the source's own
# host[:port], over the source's protocol or, for an http source, https (where
# a redirect to https on the same host takes git; libgit2's callback answers
# whatever the URL). A redirect to another host, or from https to http, gets
# nothing. It reads them from variables of git's environment, so they are in
# no helper text, command line or file. Everything it runs (test, read,
# printf) is built into sh.
_CREDENTIAL_ENV = (
    "OPAL_GIT_CREDENTIAL_PROTOCOL",
    "OPAL_GIT_CREDENTIAL_HOST",
    "OPAL_GIT_CREDENTIAL_USERNAME",
    "OPAL_GIT_CREDENTIAL_PASSWORD",
)
_CREDENTIAL_HELPER = (
    '!f() { test "$1" = get || return 0; p=; h=; '
    'while IFS= read -r l; do case "$l" in '
    "protocol=*) p=${l#protocol=};; host=*) h=${l#host=};; '') break;; "
    "esac; done; "
    'if test "$h" = "$OPAL_GIT_CREDENTIAL_HOST" && { '
    'test "$p" = "$OPAL_GIT_CREDENTIAL_PROTOCOL" || '
    'test "$p/$OPAL_GIT_CREDENTIAL_PROTOCOL" = https/http; }; then '
    "printf 'username=%s\\npassword=%s\\n' "
    '"$OPAL_GIT_CREDENTIAL_USERNAME" "$OPAL_GIT_CREDENTIAL_PASSWORD"; '
    "fi; }; f"
)
# --no-write-fetch-head: git empties FETCH_HEAD as it starts, before it has
# even connected, so a fetch that then fails or is stopped would look fresh to
# whatever reads FETCH_HEAD's age. It is rewritten only once git exited 0, as
# libgit2 does. --no-auto-maintenance: fetch would otherwise start `git
# maintenance run --auto` (a gc that detaches into a session of its own,
# outliving the op, and repacks beside OPAL's own repack).
# --no-show-forced-updates skips a check that only feeds git's progress output
# and costs time on a clone with many refs.
_FETCH_ARGS = (
    "fetch",
    "--quiet",
    "--no-tags",
    "--no-write-fetch-head",
    "--no-recurse-submodules",
    "--no-auto-maintenance",
    "--no-show-forced-updates",
)
# git clone writes the remote's refs into packed-refs in one go, where a fetch
# into a new repository writes one file per ref (half a minute for 60,000
# branches). core.logAllRefUpdates=false, kept in the clone's config: no
# reflog for any ref the clone or a later fetch writes. Given to git as well,
# so that the init clone runs, which writes true when the setting is unset,
# leaves it alone: the clone's config holds it once. --template= copies no
# template, and so no hook, into the clone. --no-tags, as for a fetch.
_CLONE_ARGS = (
    "-c",
    "core.logAllRefUpdates=false",
    "clone",
    "--quiet",
    "--no-checkout",
    "--no-tags",
    "--template=",
    "-c",
    "core.logAllRefUpdates=false",
)
# The SSH client options for every op, matching what libgit2 does today through
# pygit2. -F /dev/null: libssh2 reads no ssh_config, so neither the user's nor
# the system's (no ProxyCommand, ControlMaster or IdentityFile from there).
# BatchMode: never prompt. IdentityFile=none, before any -i: no default key of
# ~/.ssh is ever tried, even when the op's own key file cannot be read.
# LogLevel=INFO, ssh's default: ssh says why it gave up (no algorithm in
# common with the server, a server gone silent, a connection closed or reset)
# at INFO, and that goes into the op's error.
# Beyond libgit2: a connect that gets no answer fails after 30 s, and a link
# the server stays silent on (4 keepalives, 15 s apart, unanswered) after
# about a minute, with ssh's own error rather than at the op's timeout.
_SSH_OPTIONS = (
    "-F",
    "/dev/null",
    "-o",
    "BatchMode=yes",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "IdentityFile=none",
    "-o",
    "LogLevel=INFO",
    "-o",
    "ConnectTimeout=30",
    "-o",
    "ServerAliveInterval=15",
    "-o",
    "ServerAliveCountMax=4",
)
# Host keys without SCOPES_GIT_SSH_KNOWN_HOSTS: measured (see git_cli_test's
# host-key test), libgit2 through pygit2 accepts the host key of every server,
# known, unknown or changed, and records none, so ssh does the same.
_SSH_HOST_KEYS_AS_LIBGIT2 = (
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "GlobalKnownHostsFile=/dev/null",
)
# What ssh says, at INFO, of each host key it takes with the options above:
# that it added the key to known_hosts, which is /dev/null. It says so on every
# op that reaches the server, so it is left out of the op's error. ssh ends its
# lines with CRLF.
_SSH_HOST_KEY_ADDED = re.compile(
    r"^Warning: Permanently added .* to the list of known hosts\.\r?\n?",
    re.MULTILINE,
)
_HTTP_SCHEMES = ("http", "https")
_SSH_SCHEMES = ("ssh", "git+ssh", "ssh+git")
# Query parameters that carry a credential; git would send them on every
# request and print them in its errors, so such a URL is refused.
_QUERY_CREDENTIALS = ("private_token", "access_token", "token")
# Left in a clone's .git by a git killed while it updated refs, or the clone's
# config (a repack's git config). git removes its own on SIGTERM, not on
# SIGKILL. Refs locks are found under refs/.
# packed-refs.new is the packed-refs git writes (O_EXCL) while it holds
# packed-refs.lock: left behind, it fails every later rewrite of packed-refs,
# the ref deletions of a pruning fetch included.
_GIT_DIR_LOCKS = (
    "packed-refs.lock",
    "packed-refs.new",
    "FETCH_HEAD.lock",
    "shallow.lock",
    "index.lock",
    "config.lock",
)
# What a clone's reflogs dir (logs/) is renamed to, plus a random suffix, by a
# repack that removes it once it has let go of the clone (git_fetcher).
REFLOGS_SET_ASIDE = "logs.removing-"
# fetch's in-progress pack, renamed into place only once it is complete.
_PACK_TEMP_PREFIX = "tmp_"
# A .keep that index-pack writes beside a fetched pack while fetch updates the
# refs, so that no gc deletes it meanwhile: "fetch-pack <pid> on <host>".
_FETCH_KEEP_RE = re.compile(r"\Afetch-pack [0-9]+ on .*\Z")
_REMOTE_NAME_RE = re.compile(r"\A[A-Za-z0-9_][A-Za-z0-9._-]*\Z")
_GIT_VERSION_RE = re.compile(r"git version ([0-9]+)\.([0-9]+)")
_CLONE_DIR_MARK = ".clone-"
_LOCK_SUFFIX = ".lock"
# An op's lock fd is moved to at least this number, out of the way of the fd 3
# the status script uses.
_LOCK_FD_MIN = 10
_KEY_DIR_PREFIX = "opal-git-ssh-"
# An SSH key directory: the prefix, the pid of the process that made it (for
# whoever looks; whether it is still in use is told by its lock), and
# mkdtemp's random part.
_KEY_DIR_RE = re.compile(r"\Aopal-git-ssh-[0-9]+-")
_KEY_FILE = "id"
# How long a key directory that holds no key file yet is left alone by the
# sweep: an op makes its directory, then locks it, then writes the key, all
# within microseconds of each other.
_KEY_DIR_SETUP_SECONDS = 60.0
# Memory, not disk, for SSH key files where there is one to use.
_SHM = "/dev/shm"

# Tasks that finish stopping an op whose caller is gone, kept referenced so that
# the event loop does not drop them half-way.
_background: Set["asyncio.Future"] = set()
# Every clone-lock fd this process holds, and its lock file.
_lock_fds: Dict[int, Path] = {}


def background_ops() -> int:
    """How many ops are being stopped, or wait for a group to be gone, on tasks
    of their own (see drain_git_ops)."""
    return len(_background)


async def wait_for_background_ops(timeout: float) -> bool:
    """Waits up to `timeout` seconds for background_ops() to reach 0.

    Returns:
        Whether it did.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(timeout, 0.0)
    while _background:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        await asyncio.wait(set(_background), timeout=remaining)
    return True


def kill_grace_seconds() -> float:
    """SCOPES_GIT_CLI_KILL_GRACE as a finite number >= 0, else 5 (which
    validate_git_cli_settings refuses at startup)."""
    try:
        grace = float(opal_server_config.SCOPES_GIT_CLI_KILL_GRACE)
    except (TypeError, ValueError):
        return _DEFAULT_KILL_GRACE_SECONDS
    if not math.isfinite(grace) or grace < 0:
        return _DEFAULT_KILL_GRACE_SECONDS
    return grace


def known_hosts_file() -> Optional[str]:
    """SCOPES_GIT_SSH_KNOWN_HOSTS as an absolute path (a relative one is the
    server's working directory's), or None when it is unset, empty, or the git
    command-line fetch is off."""
    path = opal_server_config.SCOPES_GIT_SSH_KNOWN_HOSTS
    if not path or not opal_server_config.SCOPES_GIT_FETCH_WITH_CLI:
        return None
    return os.path.abspath(path)


def validate_git_cli_settings() -> None:
    """Check, at startup, what the git command-line fetch needs.

    With SCOPES_GIT_FETCH_WITH_CLI off it only logs an ERROR when
    SCOPES_GIT_SSH_KNOWN_HOSTS is set, which is then ignored: turning the
    CLI setting off alone, to fall back to libgit2, never stops a server.
    With it on, a uid with no entry in the user database, which ssh
    refuses to run under, is logged as an ERROR: only SSH sources fail.

    Raises:
        ValueError: with SCOPES_GIT_FETCH_WITH_CLI on, there is no git on
            PATH, or one older than 2.32, or no executable /bin/sh;
            SCOPES_GIT_CLI_KILL_GRACE is not a finite number >= 0;
            SCOPES_GIT_SSH_KNOWN_HOSTS names no readable file, or its path
            holds whitespace (which ssh would read as a list of files), % or
            $; or the directory SSH key files go to has % or $ in its path
            (ssh expands both, in a known_hosts path and in a key's).
    """
    if not opal_server_config.SCOPES_GIT_FETCH_WITH_CLI:
        if opal_server_config.SCOPES_GIT_SSH_KNOWN_HOSTS:
            logger.error(
                "SCOPES_GIT_SSH_KNOWN_HOSTS is set but SCOPES_GIT_FETCH_WITH_CLI is "
                "off: only the git command-line fetch verifies the git host's SSH "
                "key against that file, so it is ignored"
            )
        return
    grace = opal_server_config.SCOPES_GIT_CLI_KILL_GRACE
    try:
        valid_grace = math.isfinite(float(grace)) and float(grace) >= 0
    except (TypeError, ValueError):
        valid_grace = False
    if not valid_grace:
        raise ValueError(
            f"SCOPES_GIT_CLI_KILL_GRACE={grace!r}: must be a finite number of "
            "seconds, 0 or more"
        )
    _check_git_version()
    if not os.access(_SH, os.X_OK):
        raise ValueError(
            f"SCOPES_GIT_FETCH_WITH_CLI is on but {_SH} is not executable: git "
            "runs under it"
        )
    if _timeout_or_none(opal_server_config.SCOPES_GIT_FETCH_TIMEOUT) is None:
        logger.warning(
            "SCOPES_GIT_FETCH_WITH_CLI is on but SCOPES_GIT_FETCH_TIMEOUT is not "
            "positive: scope git ops have no time limit, and a hung one is never "
            "stopped"
        )
    path = known_hosts_file()
    if path is not None:
        problem = _known_hosts_problem(path)
        if problem is not None:
            raise ValueError(problem)
    key_dir_parent = _key_dir_parent()
    if _ssh_expands(key_dir_parent):
        raise ValueError(
            "SCOPES_GIT_FETCH_WITH_CLI is on but SSH key files go to "
            f"{key_dir_parent!r}, whose path holds % or $, which ssh would "
            f"expand; point TMPDIR elsewhere, or make {_SHM} writable"
        )
    _check_user_entry()


def _check_user_entry() -> None:
    """Log an ERROR when this process's uid has no entry in the user database.

    ssh looks its own user up before anything else and exits without
    one, where libssh2 needs none.
    """
    try:
        pwd.getpwuid(os.getuid())
    except KeyError:
        logger.error(
            "SCOPES_GIT_FETCH_WITH_CLI is on but uid {uid} has no entry in the "
            "user database (/etc/passwd): ssh does not run without one, so every "
            "scope source fetched over SSH fails (HTTP sources are not "
            "affected). Add an entry for the uid, or use nss_wrapper "
            "(LD_PRELOAD, NSS_WRAPPER_PASSWD, NSS_WRAPPER_GROUP), whose "
            "variables git and ssh are given",
            uid=os.getuid(),
        )


def _check_git_version() -> None:
    git = shutil.which("git")
    if git is None:
        raise ValueError("SCOPES_GIT_FETCH_WITH_CLI is on but there is no git on PATH")
    try:
        out = subprocess.run(
            [git, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_isolated_env(),
        ).stdout
    except (OSError, subprocess.SubprocessError) as e:
        raise ValueError(
            f"SCOPES_GIT_FETCH_WITH_CLI is on but {git} --version failed: {e}"
        ) from None
    match = _GIT_VERSION_RE.search(out)
    found = tuple(int(n) for n in match.groups()) if match else None
    if found is None or found < MIN_GIT_VERSION:
        needed = ".".join(map(str, MIN_GIT_VERSION))
        raise ValueError(
            f"SCOPES_GIT_FETCH_WITH_CLI is on but {git} is "
            f"{out.strip() or 'of an unknown version'}; it needs git {needed} or "
            "later"
        )


def _known_hosts_problem(path: str) -> Optional[str]:
    if any(c.isspace() for c in path):
        return (
            f"SCOPES_GIT_SSH_KNOWN_HOSTS={path!r}: the path holds whitespace, "
            "which ssh would read as more than one file"
        )
    if _ssh_expands(path):
        return (
            f"SCOPES_GIT_SSH_KNOWN_HOSTS={path!r}: the path holds % or $, which "
            "ssh would expand (%h to the host, ${VAR} to a variable)"
        )
    if not os.path.isfile(path) or not os.access(path, os.R_OK):
        return f"SCOPES_GIT_SSH_KNOWN_HOSTS={path!r}: no readable file there"
    return None


def _ssh_expands(path: str) -> bool:
    """Whether ssh would read ``path``, given as UserKnownHostsFile or -i,
    as another path: it expands % tokens and ${VAR} in both."""
    return "%" in path or "$" in path


def _timeout_or_none(timeout: float) -> Optional[float]:
    """``timeout`` for asyncio.wait: None (no limit) unless positive and
    finite, as run_in_git_executor reads it."""
    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        return None
    return timeout if math.isfinite(timeout) and timeout > 0 else None


# --- the clone lock -----------------------------------------------------------


def clone_lock_path(repo_path: Path) -> Path:
    """The lock file of a clone: beside it, named so that nothing listing the
    clones' directory for source ids takes it for one."""
    repo_path = Path(repo_path)
    return repo_path.parent / f".{repo_path.name}{_LOCK_SUFFIX}"


def take_clone_lock(repo_path: Path) -> Optional[int]:
    """An fd holding the clone's lock (an flock on its lock file), or None
    while another fd holds it, in this process or any other (git of an op whose
    process died included).

    Never blocks. The fd is close-on-exec; hand it to a child with
    pass_fds to have the child hold the lock as well. Raises OSError when
    the lock file cannot be opened.

    No at-fork handler closes it in a child forked without exec: uvloop
    forks to spawn every child, and would close it before pass_fds hands
    it on. The one process that forks without exec, the gunicorn master,
    closes any left once its preload is over (close_leftover_lock_fds).
    """
    path = clone_lock_path(repo_path)
    raw = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    try:
        fd = fcntl.fcntl(raw, fcntl.F_DUPFD_CLOEXEC, _LOCK_FD_MIN)
    finally:
        os.close(raw)
    _lock_fds[fd] = path
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        drop_clone_lock(fd)
        return None
    except BaseException:
        drop_clone_lock(fd)
        raise
    return fd


def drop_clone_lock(fd: int) -> None:
    """Close this process's fd on a clone lock; never raises.

    Closed, not unlocked: a child that inherited the fd keeps the lock
    until it exits.
    """
    _lock_fds.pop(fd, None)
    try:
        os.close(fd)
    except OSError as e:
        logger.warning("Could not close clone lock fd {fd}: {err!r}", fd=fd, err=e)


def close_leftover_lock_fds() -> int:
    """Close every clone-lock fd this process still holds, each logged as an
    ERROR; how many there were.

    For the gunicorn master once its preload is over, before it forks the
    workers: an fd left open there would hold a clone's lock in every
    worker for as long as it lives.
    """
    left = list(_lock_fds.items())
    for fd, path in left:
        logger.error(
            "A git op's lock on {path} was still open in the preload's process "
            "(fd {fd}); closing it before the workers are forked",
            path=path,
            fd=fd,
        )
        drop_clone_lock(fd)
    return len(left)


# The pid of an op (a git command-line op here, or a scope clone's repack) is
# written into its clone's lock file while the op runs, and removed when it is
# over. A lock file with content, found by whoever takes the lock next, is an op
# whose process died first: what its git left in the clone is removed before
# anything else runs there.


def mark_op_started(fd: int) -> bool:
    """Record this op in the lock file; whether the one before it never
    finished.

    Written over the record there, then cut to its length: a write that
    fails (a full disk) does not leave the file empty, so the op before
    stays recorded.
    """
    unfinished = os.fstat(fd).st_size > 0
    record = f"{os.getpid()}\n".encode()
    os.pwrite(fd, record, 0)
    os.ftruncate(fd, len(record))
    return unfinished


def mark_op_finished(fd: int) -> None:
    try:
        os.ftruncate(fd, 0)
    except OSError as e:
        logger.warning(
            "Could not clear a finished git op from its clone's lock file: {err!r}",
            err=e,
        )


def _take_and_record(repo_path: Path) -> Tuple[Optional[int], bool]:
    """take_clone_lock, then the op recorded in the lock file: the fd (None
    while another holds the lock) and whether the op before never finished.
    Blocking; for an executor thread.

    Raises:
        GitCliLocalError: the lock file cannot be opened or written.
    """
    try:
        fd = take_clone_lock(repo_path)
    except OSError as e:
        raise GitCliLocalError(128, f"fatal: cannot lock {repo_path}: {e}") from None
    if fd is None:
        return None, False
    try:
        return fd, mark_op_started(fd)
    except OSError as e:
        drop_clone_lock(fd)
        raise GitCliLocalError(
            128, f"fatal: cannot record the op in its clone's lock: {e}"
        ) from None


def _unrecord_and_drop(fd: int) -> None:
    mark_op_finished(fd)
    drop_clone_lock(fd)


def sweep_clone_leftovers(clones_dir: Path) -> None:
    """Remove what git ops whose process died left behind, for every clone in
    ``clones_dir`` (git_sources), and the SSH key directories of dead processes
    of this user.

    For the pre-fork preload, before its sync, with the git command-line
    fetch on or off: locks, partial packs and fetch ``.keep`` files of
    every clone, and every directory a clone was being made in, each under
    the clone's lock (a clone whose lock is held is left alone). A dead
    op's record stays in the clone's lock file until all of that is gone.
    A clone that cannot be read is logged and left; never raises.
    """
    remove_dead_key_dirs()
    try:
        with os.scandir(clones_dir) as entries:
            names = [e.name for e in entries]
    except FileNotFoundError:
        return  # no clones (a new pod)
    except OSError as e:
        logger.warning("Not sweeping {path}: {err!r}", path=clones_dir, err=e)
        return
    # Clones are named by source id, which holds no dot; a directory a clone
    # was being made in is ".<source id>.clone-<random>".
    targets = {n for n in names if "." not in n}
    targets |= {
        n[1:].split(_CLONE_DIR_MARK, 1)[0]
        for n in names
        if n.startswith(".") and _CLONE_DIR_MARK in n
    }
    for name in sorted(targets):
        repo_path = Path(clones_dir) / name
        try:
            _sweep_clone(repo_path)
        except OSError as e:
            logger.warning("Not sweeping {path}: {err!r}", path=repo_path, err=e)


def _sweep_clone(repo_path: Path) -> None:
    fd = take_clone_lock(repo_path)
    if fd is None:
        logger.warning(
            "Not sweeping {path}: a git op of another process holds it",
            path=repo_path,
        )
        return
    try:
        # A record of a dead op stays until what it left is all gone.
        if remove_dead_op_leftovers(repo_path):
            mark_op_finished(fd)
    finally:
        drop_clone_lock(fd)


def remove_dead_op_leftovers(repo_path: Path) -> bool:
    """Remove what any git op of ``repo_path`` whose process died can have
    left: what a killed fetch leaves in the clone (remove_kill_leftovers)
    and the directories its clones were being made in (_remove_clone_dirs);
    whether all of it is gone. For the holder of the clone's lock.

    A git dir that cannot be looked at (EACCES, EIO) counts as not all
    gone, so that the dead op stays recorded: Path.is_dir() raises then
    on Python 3.11 and 3.12, and os.path.isdir() says there is none.
    """
    git_dir = repo_path / ".git"
    complete = True
    try:
        has_git_dir = stat.S_ISDIR(os.stat(git_dir).st_mode)
    except (FileNotFoundError, NotADirectoryError):
        has_git_dir = False
    except OSError as e:
        logger.warning("Could not look at {path}: {err!r}", path=git_dir, err=e)
        has_git_dir = complete = False
    if has_git_dir:
        complete = remove_kill_leftovers(repo_path)
    return _remove_clone_dirs(repo_path) and complete


def clean_up_unfinished_op(repo_path: Path) -> None:
    """For a libgit2 fetch, which takes no clone lock: when the clone's lock
    file records an op that never finished (its process died, a repack killed
    with its container while pack-refs ran, say), remove what it left, as a git
    command-line op does before it starts (remove_dead_op_leftovers), and clear
    the record once all of it is gone; while some of it is not, the record
    stays, for the next op to try again.

    Under the clone's lock, and only when nothing else holds it. Never
    raises.
    """
    try:
        fd = take_clone_lock(repo_path)
    except OSError as e:
        # DEBUG: where flock fails (NFS without local_lock=flock) it fails on
        # every fetch, and each repack already logs it.
        logger.debug(
            "Could not lock {path} to look for a git op that never finished: {err!r}",
            path=repo_path,
            err=e,
        )
        return
    if fd is None:
        # An op holds it, and cleans up after a dead one itself.
        logger.debug(
            "Not looking for a git op on {path} that never finished: another op "
            "holds its lock",
            path=repo_path,
        )
        return
    try:
        if os.fstat(fd).st_size == 0:
            return
        logger.warning(
            "The last git op on {path} never finished (its process died): "
            "removing what it left",
            path=repo_path,
        )
        if remove_dead_op_leftovers(repo_path):
            mark_op_finished(fd)
        else:
            logger.warning(
                "Leaving the git op on {path} recorded in its lock file: what it "
                "left could not all be removed, and the next op on it tries again",
                path=repo_path,
            )
    except OSError as e:
        logger.warning(
            "Could not check {path} for a git op that never finished: {err!r}",
            path=repo_path,
            err=e,
        )
    finally:
        drop_clone_lock(fd)


def clone_under_way(repo_path: Path) -> bool:
    """Whether a directory a clone of ``repo_path`` is being made in sits
    beside it: a git command-line clone, renamed to ``repo_path`` once
    complete, or what one whose process died left (until the next op on the
    clone, or the preload, removes it).

    Read from disk, so that every worker gives the same answer; False when
    the directory cannot be listed.
    """
    prefix = f".{repo_path.name}{_CLONE_DIR_MARK}"
    try:
        with os.scandir(repo_path.parent) as entries:
            return any(
                e.name.startswith(prefix) and e.is_dir(follow_symlinks=False)
                for e in entries
            )
    except OSError:
        return False


def _remove_clone_dirs(repo_path: Path) -> bool:
    """Remove every directory a clone of ``repo_path`` was being made in; for a
    holder of the clone's lock, under which no clone of it is under way.

    Whether all of them are gone.
    """
    prefix = f".{repo_path.name}{_CLONE_DIR_MARK}"
    try:
        with os.scandir(repo_path.parent) as entries:
            names = [e.name for e in entries if e.name.startswith(prefix)]
    except FileNotFoundError:
        return True
    except OSError as e:
        logger.warning("Could not list {path}: {err!r}", path=repo_path.parent, err=e)
        return False
    complete = True
    for name in names:
        path = repo_path.parent / name
        try:
            if not stat.S_ISDIR(os.lstat(path).st_mode):
                continue
        except FileNotFoundError:
            continue
        except OSError as e:
            logger.warning("Could not look at {path}: {err!r}", path=path, err=e)
            complete = False
            continue
        logger.info("Removing {path}, left by a clone that never finished", path=path)
        complete = remove_tree(path) and complete
    return complete


# --- the ops ------------------------------------------------------------------


# How an op ended, as its on_gone is told: True, it succeeded; False, it failed
# or was stopped, its process group is gone and what it left in the clone has
# been removed (when some of it could not be, the op stays recorded in the
# clone's lock file, for the next op to try again); None, the event loop ended
# while it was being stopped: its group got SIGKILL there and then, and what it
# left is for the next op on the clone to remove (the op stays recorded in the
# clone's lock file).
OnGone = Callable[[Optional[bool]], None]


async def cli_fetch(
    repo_path: Path,
    remote: str,
    source: GitPolicyScopeSource,
    *,
    prune: bool,
    timeout: float,
    on_gone: Optional[OnGone] = None,
) -> None:
    """Fetch ``remote`` into the clone at ``repo_path`` with ``git fetch``.

    The remote's URL and refspecs are read from the clone's config, as
    libgit2 reads them. Tags are not fetched. FETCH_HEAD is rewritten
    (empty) only once git exited 0; a fetch that fails or is
    stopped leaves it as it was. A FETCH_HEAD that cannot be written then (a
    full disk) is logged at ERROR, and the fetch still counts as one that
    succeeded. A fetch that git ends with an error of its own (a full disk)
    leaves none of the temp files of the pack it was writing, nor a .keep
    without its pack.

    Args:
        repo_path: The clone (non-bare; its git dir is ``repo_path/.git``).
        remote: The remote's name in the clone's config.
        source: The scope source the clone belongs to, for its credentials.
        prune: Remove the refs the refspecs map to whose branch is gone on
            the remote (--prune).
        timeout: Seconds before git is stopped; 0 or less, or not finite,
            means no limit.
        on_gone: Called exactly once, however the op ends (see OnGone),
            once nothing of the op is left: its process group gone, what it
            left in the clone removed and the clone's lock released. That
            can be after this returns or raises (a stop under way, a
            process that outlived SIGKILL).

    Raises:
        GitCliTimeoutError: git ran past ``timeout`` and was stopped (SIGTERM
            to its process group, SIGKILL SCOPES_GIT_CLI_KILL_GRACE seconds
            later). A TimeoutError.
        GitCliBusyError: another op holds the clone's lock.
        GitCliLocalError: the op failed locally (see that class).
        GitCliError: git exited non-zero.
        ValueError: ``remote`` cannot be given to git.
    """
    repo_path = Path(repo_path)
    # The pack dir's leftovers as the op starts, under its lock: none of them
    # is this op's to remove.
    pack_leftovers_before: FrozenSet[str] = frozenset()

    def _clean_up(status: Optional[int]) -> bool:
        if killed_by_signal(status):
            return remove_kill_leftovers(repo_path)
        # git's own error exit (a full disk, say) rolls back its locks, not the
        # temp files of the pack it was writing, which would keep the disk full.
        return _remove_new_pack_leftovers(repo_path, pack_leftovers_before)

    op = _Op(f"fetch of {repo_path}", repo_path, on_gone, clean_up=_clean_up)
    try:
        _check_remote(remote)
        url, refspecs = await _run_local(_remote_config, repo_path, remote)
        remote_for_git = _remote_for_git(url, source)
        await op.start()
        pack_leftovers_before = await _run_local(_pack_leftovers, repo_path)
    except BaseException:
        await op.not_started()
        raise
    args = [
        "-C",
        os.fspath(repo_path),
        *_GIT_CONFIG_ARGS,
        *_FETCH_ARGS,
        "--prune" if prune else "--no-prune",
        # Ends git's options: neither the URL nor a refspec can be taken for one.
        "--",
        remote_for_git.url,
        *refspecs,
    ]
    await _run_op(op, args, source, remote_for_git, timeout)

    def _empty_fetch_head() -> None:
        fetch_head = repo_path / ".git" / "FETCH_HEAD"
        try:
            fetch_head.write_bytes(b"")
        except OSError as e:
            # git fetched; only the mark of when it did is missing. What
            # reads FETCH_HEAD's age (a liveness probe) notices a disk that
            # stays full.
            logger.error(
                "Could not rewrite {path} after a fetch that succeeded: {err!r}",
                path=fetch_head,
                err=e,
            )

    await op.finish(succeeded=True, then=_empty_fetch_head)


async def cli_clone(
    url: str,
    repo_path: Path,
    source: GitPolicyScopeSource,
    *,
    remote: str,
    timeout: float,
    on_gone: Optional[OnGone] = None,
) -> None:
    """Clone ``url`` to ``repo_path`` with ``git clone``, into a directory
    beside ``repo_path`` that is renamed to it once complete.

    git is given ``url`` without its user and password; the clone's remote
    then gets ``url`` itself, as a libgit2 clone has it (the fetcher checks
    it against the source's URL). The clone has no checkout, which the
    scopes fetcher does not read, and, like a libgit2 clone, an empty
    FETCH_HEAD. Directories left beside ``repo_path`` by clones whose
    process died are removed first, and the new one is removed whatever
    keeps the clone from being put in place.

    Args:
        url: The remote's URL.
        repo_path: Where the clone goes. It must not exist, or be empty.
        source: The scope source, for its credentials.
        remote: The remote's name in the clone.
        timeout: Seconds before git is stopped; 0 or less, or not finite,
            means no limit.
        on_gone: As for cli_fetch.

    Raises:
        GitCliTimeoutError: git ran past ``timeout`` and was stopped; the
            new directory is removed once git's process group is gone. A
            TimeoutError.
        GitCliBusyError: another op holds the clone's lock.
        GitCliLocalError: the op failed locally, ``repo_path`` exists and
            is not empty included.
        GitCliError: git exited non-zero; the new directory is removed.
        ValueError: ``remote`` cannot be given to git.
    """
    repo_path = Path(repo_path)
    new_dir = repo_path.parent / (
        f".{repo_path.name}{_CLONE_DIR_MARK}{secrets.token_hex(8)}"
    )
    op = _Op(
        f"clone into {repo_path}",
        repo_path,
        on_gone,
        clean_up=lambda status: remove_tree(new_dir),
        on_unstarted=lambda: remove_tree(new_dir),
    )
    try:
        _check_remote(remote)
        remote_for_git = _remote_for_git(url, source)
        await _run_local(_make_parent, repo_path)
        await op.start()
        await _run_local(_make_clone_dir, repo_path, new_dir)
    except BaseException:
        await op.not_started()
        raise
    args = [
        *_GIT_CONFIG_ARGS,
        *_CLONE_ARGS,
        "--origin",
        remote,
        "--",
        remote_for_git.url,
        os.fspath(new_dir),
    ]
    await _run_op(op, args, source, remote_for_git, timeout)
    await op.finish(
        succeeded=True,
        then=lambda: _place_clone(new_dir, repo_path, remote, url, op.remove_left),
    )


def _off_loop(func, *args) -> "asyncio.Future":
    """``func(*args)`` on the event loop's executor; once that is shut down, as
    the loop ends (asyncio.run shuts it down before it closes the loop), on the
    loop's own thread, so that an op the end overtakes is still finished."""
    loop = asyncio.get_running_loop()
    try:
        return loop.run_in_executor(None, func, *args)
    except RuntimeError:  # the executor is shut down
        done = loop.create_future()
        try:
            done.set_result(func(*args))
        except Exception as e:
            done.set_exception(e)
        return done


async def _run_local(func, *args):
    """``func(*args)`` off the event loop (_off_loop), with an OSError or a
    pygit2 error out of it turned into GitCliLocalError."""
    try:
        return await _off_loop(func, *args)
    except GitCliError:
        raise
    except (OSError, pygit2.GitError) as e:
        raise GitCliLocalError(128, f"fatal: {e}") from None


def _make_parent(repo_path: Path) -> None:
    repo_path.parent.mkdir(parents=True, exist_ok=True)


def _make_clone_dir(repo_path: Path, new_dir: Path) -> None:
    """Make the directory a clone into ``repo_path`` goes in, for the holder of
    its lock.

    Raises:
        GitCliLocalError: ``repo_path`` exists and is not empty.
    """
    if _exists_and_not_empty(repo_path):
        raise GitCliLocalError(
            128,
            f"fatal: destination path '{repo_path}' already exists and is not "
            "an empty directory.",
        )
    new_dir.mkdir()


async def _run_op(
    op: "_Op",
    args: List[str],
    source: GitPolicyScopeSource,
    remote: "_Remote",
    timeout: float,
) -> None:
    """Run git for ``op``, which holds its clone's lock; return once git exited
    0, with the op still to finish (see _run_git)."""
    running = False
    try:
        with _git_env(source, remote) as (env, redact):
            running = True
            await _run_git(args, env=env, timeout=timeout, redact=redact, op=op)
    except BaseException:
        if not running:  # git's environment could not be set up
            await op.not_started()
        raise


async def _take_clone_lock_off_loop(repo_path: Path) -> Optional[int]:
    """take_clone_lock off the event loop (_off_loop).

    A caller cancelled meanwhile
    leaves no fd behind: the one the thread took is dropped once it is
    there.
    """
    work = _off_loop(take_clone_lock, repo_path)
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        work.add_done_callback(_drop_taken_lock)
        raise


def _drop_taken_lock(work: "asyncio.Future") -> None:
    if not work.cancelled() and work.exception() is None and work.result() is not None:
        drop_clone_lock(work.result())


def _nothing_left() -> bool:
    return True


@dataclass
class _Op:
    """One op's hold on its clone: the clone's lock, taken in ``start`` and
    released in ``finish`` (or ``not_started``), which also removes what the op
    left when it needs to and calls ``on_gone``, exactly once.

    The op stays recorded in the lock file, for the next op on the clone
    to try again, when anything it or a dead op before it left could not
    all be removed. Every file it touches, the lock's included, is
    touched off the event loop (_off_loop).
    """

    what: str
    repo_path: Path
    on_gone: Optional[OnGone]
    # What to remove, under the lock, after a git that did not succeed (by its
    # exit status, None for a stopped one); whether all of it is gone.
    clean_up: Callable[[Optional[int]], bool]
    # The same when git never ran.
    on_unstarted: Callable[[], bool] = _nothing_left
    lock_fd: Optional[int] = None
    _done: bool = False
    _starting: Optional["asyncio.Future"] = None
    _left_behind: bool = False

    async def start(self) -> None:
        """Take the clone's lock, and record the op in it. When the last op
        recorded there never finished (its process died), first remove what it
        left.

        Raises:
            GitCliBusyError: another op holds the lock.
            GitCliLocalError: the lock file cannot be opened or written.
        """
        self._starting = _off_loop(self._take_lock)
        if not await asyncio.shield(self._starting):
            raise GitCliBusyError(
                128,
                f"fatal: another git op holds {self.repo_path}: one of another "
                "process, or one whose process died and whose git has not exited",
            )

    def _take_lock(self) -> bool:
        fd, unfinished = _take_and_record(self.repo_path)
        if fd is None:
            return False
        self.lock_fd = fd
        if unfinished:
            logger.warning(
                "The last git op on {path} never finished (its process died): "
                "removing what it left",
                path=self.repo_path,
            )
            if not remove_dead_op_leftovers(self.repo_path):
                self._left_behind = True
        return True

    def remove_left(self, status: Optional[int]) -> None:
        """``clean_up``, noting what it could not remove."""
        if not self.clean_up(status):
            self._left_behind = True

    def _end_hold(self, fd: int) -> None:
        """Drop the lock fd; the op's record in the lock file goes with it
        unless something left in the clone could not be removed."""
        if not self._left_behind:
            _unrecord_and_drop(fd)
            return
        logger.warning(
            "Leaving the git op on {path} recorded in its lock file: what was "
            "left in the clone could not all be removed, and the next op on it "
            "tries again",
            path=self.repo_path,
        )
        drop_clone_lock(fd)

    async def not_started(self) -> None:
        """git did not run: once ``start``'s work is over, remove what
        ``on_unstarted`` names and release the lock if it is held, then tell
        the caller. Seen through even when the caller is cancelled
        meanwhile."""
        if self._done:
            return
        self._done = True
        work = _keep(self._release_unstarted())
        work.add_done_callback(lambda f: self._call_on_gone(False))
        await asyncio.shield(work)

    async def _release_unstarted(self) -> None:
        if self._starting is not None:
            # Done or not, start's work sets lock_fd (or not) before it ends.
            await asyncio.wait({self._starting})
        fd, self.lock_fd = self.lock_fd, None
        if fd is not None:
            await _off_loop(self._unstarted_clean_up, fd)

    def _unstarted_clean_up(self, fd: int) -> None:
        try:
            if not self.on_unstarted():
                self._left_behind = True
        finally:
            self._end_hold(fd)

    async def finish(
        self,
        *,
        succeeded: bool,
        status: Optional[int] = None,
        then: Optional[Callable[[], None]] = None,
    ) -> None:
        """git ran and its group is gone: remove what it left when it did not
        succeed (``clean_up`` decides by ``status``, which is None for a
        stopped git, or one whose status never came back), run ``then``,
        release the lock, then call on_gone. The work runs off the event loop
        (_off_loop) and is seen through even when the caller is cancelled
        meanwhile.

        Raises:
            GitCliLocalError: ``then`` failed with an OSError.
        """
        if self._done:
            return
        self._done = True
        work = _off_loop(self._release, succeeded, status, then)
        work.add_done_callback(
            lambda f: self._call_on_gone(
                succeeded and not f.cancelled() and f.exception() is None
            )
        )
        try:
            await asyncio.shield(work)
        except OSError as e:
            raise GitCliLocalError(128, f"fatal: {e}") from None

    def _release(
        self, succeeded: bool, status: Optional[int], then: Optional[Callable]
    ) -> None:
        try:
            if not succeeded:
                self.remove_left(status)
            if then is not None:
                then()
        finally:
            fd, self.lock_fd = self.lock_fd, None
            if fd is not None:
                self._end_hold(fd)

    def abandon(self) -> None:
        """The event loop is ending: close the lock fd (git, if still alive,
        holds its own copy), and leave the op recorded in the lock file, so
        that the next op on the clone removes what this one left. on_gone is
        told None: nothing says the group is gone."""
        if self._done:
            return
        if self.lock_fd is not None:
            drop_clone_lock(self.lock_fd)
            self.lock_fd = None
        self._call_on_gone(None)

    async def finish_once_unlocked(self) -> None:
        """Finish an op whose group is not known (its start was cancelled, or
        failed once sh may have been running).

        Closes this process's fd on the lock, waits until no process
        holds it any more, then finishes under a lock of its own. Another
        process can take the lock meanwhile, record its op in place of this
        one's and die, leaving more than this op's ``clean_up`` removes (a
        clone half made): what any dead op can leave goes as well
        (remove_dead_op_leftovers), and the record stays while some of it
        does not.
        """
        if self._done:
            return
        if self.lock_fd is not None:
            drop_clone_lock(self.lock_fd)
            self.lock_fd = None
        interval = _GROUP_POLL_SECONDS
        waited = 0.0
        try:
            while True:
                fd = await _take_clone_lock_off_loop(self.repo_path)
                if fd is not None:
                    break
                await asyncio.sleep(interval)
                waited += interval
                if waited >= KILL_WAIT_SECONDS:
                    interval = _LOCK_POLL_SECONDS
        except asyncio.CancelledError:
            self._call_on_gone(None)
            raise
        except Exception as e:
            # Nothing else will ever end this op: on_gone is called here, and
            # the op stays recorded in the lock file for the next op to clean
            # up after.
            logger.error(
                "Could not lock {path} to clean up after a git op whose start "
                "was given up on: {err!r}",
                path=self.repo_path,
                err=e,
            )
            self._call_on_gone(False)
            return
        self.lock_fd = fd
        await self.finish(
            succeeded=False, status=None, then=self._remove_dead_op_leftovers
        )

    def _remove_dead_op_leftovers(self) -> None:
        """remove_dead_op_leftovers, noting what it could not remove."""
        if not remove_dead_op_leftovers(self.repo_path):
            self._left_behind = True

    def _call_on_gone(self, how: Optional[bool]) -> None:
        self._done = True
        on_gone, self.on_gone = self.on_gone, None
        if on_gone is None:
            return
        try:
            on_gone(how)
        except Exception as e:
            logger.error("on_gone of git {what} raised: {err!r}", what=self.what, err=e)


def _check_remote(remote: str) -> None:
    if not _REMOTE_NAME_RE.match(remote):
        raise ValueError(f"not a remote name git can be given: {remote!r}")


def _remote_config(repo_path: Path, remote: str) -> Tuple[str, List[str]]:
    """The URL and fetch refspecs of ``remote`` in the clone's config (its
    default refspec when it has none)."""
    try:
        repo = pygit2.Repository(os.fspath(repo_path))
    except pygit2.GitError as e:
        raise GitCliLocalError(128, f"fatal: not a git repository: {e}") from None
    try:
        try:
            configured = repo.remotes[remote]
        except KeyError:
            raise GitCliLocalError(
                128, f"fatal: '{remote}' is not a remote of {repo_path}"
            ) from None
        url = configured.url
        refspecs = list(configured.fetch_refspecs) or [
            f"+refs/heads/*:refs/remotes/{remote}/*"
        ]
    finally:
        repo.free()
    if not url:
        raise GitCliLocalError(128, f"fatal: remote '{remote}' has no URL")
    return url, refspecs


def _exists_and_not_empty(path: Path) -> bool:
    try:
        with os.scandir(path) as entries:
            return any(True for _ in entries)
    except FileNotFoundError:
        return False
    except NotADirectoryError:
        return True


def _place_clone(
    new_dir: Path,
    repo_path: Path,
    remote: str,
    url: str,
    remove: Callable[[Optional[int]], None],
) -> None:
    """Give the filled clone its remote's URL and an empty FETCH_HEAD, and
    rename it into place; on failure, ``remove`` it."""
    try:
        repo = pygit2.Repository(os.fspath(new_dir))
        try:
            repo.remotes.set_url(remote, url)
        finally:
            repo.free()
        (new_dir / ".git" / "FETCH_HEAD").touch()
        os.rename(new_dir, repo_path)
    except (OSError, pygit2.GitError) as e:
        remove(None)
        raise GitCliLocalError(
            128, f"fatal: could not put the clone in place at '{repo_path}': {e}"
        ) from None


def remove_tree(path: Path) -> bool:
    """``shutil.rmtree(path)``; whether ``path`` is gone.

    Logged, never raised.
    """
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning("Could not remove {path}: {err!r}", path=path, err=e)
        return False
    return True


def _pack_leftovers(repo_path: Path) -> FrozenSet[str]:
    """The files of the clone's pack dir a fetch can leave behind: the temp
    files of a pack git has not renamed into place (``tmp_pack_*``,
    ``tmp_idx_*``), and the ``.keep`` files of packs."""
    try:
        with os.scandir(repo_path / ".git" / "objects" / "pack") as entries:
            return frozenset(
                e.name
                for e in entries
                if e.name.startswith(_PACK_TEMP_PREFIX)
                or (e.name.startswith("pack-") and e.name.endswith(".keep"))
            )
    except FileNotFoundError:
        return frozenset()


def _remove_new_pack_leftovers(repo_path: Path, before: FrozenSet[str]) -> bool:
    """Remove the pack dir's leftovers not in ``before``; whether all of them
    are gone.

    They are those of an op that git ended with an error of its own. A
    ``.keep`` stays with a pack that is complete (its .pack and .idx in
    place). For the holder of the clone's lock, once the op's group is
    gone.
    """
    pack_dir = repo_path / ".git" / "objects" / "pack"
    try:
        left = _pack_leftovers(repo_path) - before
    except OSError as e:
        logger.warning("Could not list {path}: {err!r}", path=pack_dir, err=e)
        return False
    complete = True
    for name in sorted(left):
        path = pack_dir / name
        if name.endswith(".keep"):
            stem = name[: -len(".keep")]
            if (pack_dir / f"{stem}.pack").exists() and (
                pack_dir / f"{stem}.idx"
            ).exists():
                continue
        try:
            os.unlink(path)
        except FileNotFoundError:
            continue
        except OSError as e:
            logger.warning(
                "Could not remove {path}, left by a git fetch that failed: {err!r}",
                path=path,
                err=e,
            )
            complete = False
            continue
        logger.info("Removed {path}, left by a git fetch that failed", path=path)
    return complete


# The highest signal number sh reports as 128 plus it; Linux's go to 64.
_MAX_SIGNAL = 64


def killed_by_signal(status: Optional[int]) -> bool:
    """Whether a git exit ``status`` is a death by a signal: no status at all
    (git's sh was killed first), a negative one (a Popen's for a signal), or
    sh's 128 plus the signal.

    Not git's own 255, which some of its fatal paths exit with (a
    config.lock it cannot take): what it left is its own to clean up,
    and the locks it found held may be live.
    """
    if status is None or status < 0:
        return True
    return 128 < status <= 128 + _MAX_SIGNAL


def remove_kill_leftovers(repo_path: Path) -> bool:
    """Remove what a git fetch, or a repack's git config or git pack-refs,
    killed by a signal can leave in a clone; whether all of it is gone (False:
    some of it could not be listed or removed, each logged).

    Run only by the holder of the clone's lock, with no other op's process
    left, and only inside this clone's git dir: the lock files of the refs
    it was updating, of packed-refs, FETCH_HEAD, shallow, the index and the
    config, the packed-refs.new it was writing under packed-refs.lock, a
    fetch's partial pack (``objects/pack/tmp_*``; a repack, which also holds
    the clone's lock, cannot be writing one), and the ``.keep`` index-pack
    writes beside a pack until fetch has updated the refs. A stale lock or
    packed-refs.new fails every later fetch that has to write them, and a
    pack with a ``.keep`` is never merged by a repack. Never raises.

    Such a ``.keep`` names the pid and host of its fetch, and is removed
    whatever they are: only a git command-line fetch writes one, and that
    fetch holds the clone's lock, which needs a filesystem where flock
    works, for as long as any of its processes lives. A pid can be handed
    out again (a container restart in the same pod keeps the host name),
    and a host name can be another pod's (a volume of clones mounted by a
    new one), so neither says whether the fetch is alive; the lock does.
    """
    git_dir = repo_path / ".git"
    doomed: List[Path] = [git_dir / name for name in _GIT_DIR_LOCKS]
    ref_locks, complete = _ref_locks(git_dir / "refs")
    doomed += ref_locks
    pack_dir = git_dir / "objects" / "pack"
    try:
        with os.scandir(pack_dir) as entries:
            names = [e.name for e in entries if e.is_file(follow_symlinks=False)]
    except FileNotFoundError:
        names = []
    except OSError as e:
        logger.warning("Could not list {path}: {err!r}", path=pack_dir, err=e)
        names = []
        complete = False
    for name in names:
        if name.startswith(_PACK_TEMP_PREFIX) or (
            name.startswith("pack-")
            and name.endswith(".keep")
            and _is_fetch_keep(pack_dir / name)
        ):
            doomed.append(pack_dir / name)
    for path in doomed:
        try:
            os.unlink(path)
        except FileNotFoundError:
            continue
        except OSError as e:
            logger.warning(
                "Could not remove {path}, left by a git op that was killed: "
                "later fetches of this clone fail while it is there: {err!r}",
                path=path,
                err=e,
            )
            complete = False
            continue
        logger.info("Removed {path}, left by a git op that was killed", path=path)
    return complete


def _ref_locks(refs_dir: Path) -> Tuple[List[Path], bool]:
    """The lock files under ``refs_dir``, and whether every directory there
    could be listed."""
    locks = []
    complete = True
    directories = [refs_dir]
    while directories:
        directory = directories.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(Path(entry.path))
                    elif entry.name.endswith(".lock"):
                        locks.append(Path(entry.path))
        except FileNotFoundError:
            continue
        except OSError as e:
            logger.warning("Could not list {path}: {err!r}", path=directory, err=e)
            complete = False
    return locks, complete


def _is_fetch_keep(keep: Path) -> bool:
    """Whether ``keep`` is the ``.keep`` of a fetch; not one that cannot be
    read, nor one a person wrote to keep a pack."""
    try:
        with open(keep, encoding="utf-8", errors="replace") as f:
            text = f.read(4096).strip()
    except OSError:
        return False
    return _FETCH_KEEP_RE.match(text) is not None


@dataclass
class _Remote:
    """How git is pointed at a remote: the URL it is given, without the user
    and password; the protocol, host[:port], user and password the credential
    helper gives for an HTTP remote that has them; and every secret to
    redact from what git prints."""

    url: str
    credential: Optional[Tuple[str, str, str, str]] = field(default=None, repr=False)
    secrets: List[str] = field(default_factory=list, repr=False)

    @property
    def is_ssh(self) -> bool:
        """Whether git reaches this remote through ssh: an ssh:// URL, or
        git's scp-like ``[user@]host:path`` (a colon before any slash)."""
        scheme, sep, _ = self.url.partition("://")
        if sep:
            return scheme.lower() in _SSH_SCHEMES
        colon, slash = self.url.find(":"), self.url.find("/")
        return colon > 0 and (slash == -1 or colon < slash)


def _remote_for_git(url: str, source: GitPolicyScopeSource) -> _Remote:
    """Split the credentials off ``url`` the way libgit2 uses them: a user and
    password in an HTTP URL first, else the source's token as user ``git``
    (GitCallback's UserPass), else the URL's user alone with an empty password.

    The password and the token are secrets to redact, and so is the user of
    an HTTP URL with no password, which can be a token; not the user of a
    URL with a password, nor ``git``.

    Raises:
        GitCliRefusedSourceError: a URL git cannot be given without a
            credential on its command line: one that does not parse, an
            scp-like one with a password, one with a credential in its
            query string, or a non-HTTP one whose user, which stays in it,
            holds the password.
    """
    if "://" not in url and "@" in url:
        userinfo = url.split("@", 1)[0]
        if ":" in userinfo and "/" not in userinfo:
            raise GitCliRefusedSourceError(
                128,
                "fatal: an scp-like URL with a password cannot be given to git; "
                "use an SSH key",
            )
    try:
        parts = urlsplit(url)
        user, password = parts.username, parts.password
        parts.port  # noqa: B018 (validates it)
    except ValueError:
        raise GitCliRefusedSourceError(
            128, "fatal: the source's URL does not parse"
        ) from None
    if any(k.lower() in _QUERY_CREDENTIALS for k, _ in parse_qsl(parts.query)):
        raise GitCliRefusedSourceError(
            128,
            "fatal: the source's URL carries a credential in its query string; "
            "use the source's token auth instead",
        )
    remote = _Remote(url)
    scheme = parts.scheme.lower()
    host = parts.netloc.rpartition("@")[2]
    username_password: Optional[Tuple[str, str]] = None
    if user is not None or password is not None:
        passwords = {password, unquote(password)} if password else set()
        remote.secrets += passwords
        if scheme in _HTTP_SCHEMES and not password and user and unquote(user) != "git":
            remote.secrets += {user, unquote(user)}
        if scheme in _HTTP_SCHEMES:
            remote.url = urlunsplit(parts._replace(netloc=host))
            if password is not None:
                username_password = (unquote(user or ""), unquote(password))
        elif password is not None:
            # An SSH URL's password is no use to ssh: keep only the user,
            # unless it holds the password.
            netloc = f"{user}@{host}" if user else host
            remote.url = urlunsplit(parts._replace(netloc=netloc))
            users = {user, unquote(user)} if user else set()
            if any(p in u for p in passwords for u in users):
                raise GitCliRefusedSourceError(
                    128,
                    "fatal: the password cannot be taken out of the source's URL",
                )
    if (
        username_password is None
        and scheme in _HTTP_SCHEMES
        and isinstance(source.auth, GitHubTokenAuthData)
    ):
        username_password = ("git", source.auth.token)
        remote.secrets.append(source.auth.token)
    if username_password is None and scheme in _HTTP_SCHEMES and user is not None:
        # A user alone (a token as the user, say): libgit2 sends it with an
        # empty password.
        username_password = (unquote(user), "")
    if username_password is not None:
        # Basic credentials, should a server echo the header back.
        encoded = base64.b64encode(":".join(username_password).encode()).decode()
        remote.secrets.append(encoded)
        username, secret = username_password
        remote.credential = (scheme, host, username, secret)
    return remote


def _ssh_host_key_options(remote: _Remote) -> List[str]:
    """The host-key options of ssh: verified against SCOPES_GIT_SSH_KNOWN_HOSTS
    when it is set (and never written to), else as libgit2 does it.

    Raises:
        GitCliLocalError: the known_hosts file cannot be read, for an SSH
            remote.
    """
    path = known_hosts_file()
    if path is None:
        return list(_SSH_HOST_KEYS_AS_LIBGIT2)
    if remote.is_ssh:
        problem = _known_hosts_problem(path)
        if problem is not None:
            raise GitCliLocalError(128, f"fatal: {problem}")
    return [
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={path}",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "UpdateHostKeys=no",
    ]


def _safe_directories() -> List[str]:
    """safe.directory in the system, XDG and global git config, in that order,
    as libgit2 reads them for its own check of a clone's owner (pygit2's search
    paths: /etc, ~/.config/git and ~).

    git here reads none of those configs, so these values are given to
    it with the op's own config, where git 2.38 and later honour them. A
    config that is not there or cannot be read gives none.
    """
    found: List[str] = []
    for open_config in (
        pygit2.Config.get_system_config,
        pygit2.Config.get_xdg_config,
        pygit2.Config.get_global_config,
    ):
        try:
            found += open_config().get_multivar("safe.directory")
        except (OSError, pygit2.GitError):
            continue
    return found


def _isolated_env() -> Dict[str, str]:
    """The environment git gets whatever the op: no system or global git
    config (libgit2 reads them, but they would bring hooks, helpers, headers
    and proxies to every op; their safe.directory is given to git in
    _git_env), only the transports libgit2 speaks, the CA settings libgit2's
    OpenSSL would use, nss_wrapper's variables, and no prompt."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k in _ENV_ALLOWLIST or k.startswith(_ENV_ALLOWED_PREFIX)
    }
    for openssl, git in _CA_ENV:
        if git not in env and os.environ.get(openssl):
            env[git] = os.environ[openssl]
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    # A HOME with nothing in it: libcurl, under git's HTTP transport, would
    # send the credentials ~/.netrc has for the host, which libgit2 never
    # reads. ssh takes its home from the user database, not from HOME, and
    # its known_hosts and config here come from settings or flags.
    env["HOME"] = os.devnull
    env["GIT_ALLOW_PROTOCOL"] = _ALLOWED_PROTOCOLS
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = shutil.which("false", path=env.get("PATH")) or "/bin/false"
    env["LC_ALL"] = "C"
    return env


@contextmanager
def _git_env(
    source: GitPolicyScopeSource, remote: _Remote
) -> Iterator[Tuple[Dict[str, str], Callable[[str], str]]]:
    """The environment of git for one op, and a function that redacts the op's
    credentials from text.

    The SSH key file, in a directory of its own, is removed on the way
    out, whatever happened.

    Raises:
        GitCliLocalError: SCOPES_GIT_SSH_KNOWN_HOSTS cannot be read, or the
            key file cannot be written.
        GitCliRefusedSourceError: a user or password holds a newline, which
            git's credential protocol cannot carry.
    """
    env = _isolated_env()
    # An empty credential.helper first drops every helper of the clone's own
    # config (the system's and the user's are not read): libgit2 never runs
    # one, so neither may git. No hook runs, whatever the clone's config says.
    config = [
        ("credential.helper", ""),
        ("credential.useHttpPath", "false"),
        ("core.hooksPath", os.devnull),
    ]
    config += [("safe.directory", path) for path in _safe_directories()]
    if remote.credential is not None:
        if any("\n" in part or "\0" in part for part in remote.credential):
            raise GitCliRefusedSourceError(
                128, "fatal: a user or password with a newline cannot be given to git"
            )
        config.append(("credential.helper", _CREDENTIAL_HELPER))
        env.update(zip(_CREDENTIAL_ENV, remote.credential))
    env["GIT_CONFIG_COUNT"] = str(len(config))
    for i, (key, value) in enumerate(config):
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value
    # Longest first: a secret inside another one would leave the rest of it.
    hidden = sorted({s for s in remote.secrets if s}, key=len, reverse=True)

    def redact(text: str) -> str:
        for secret in hidden:
            text = text.replace(secret, "***")
        return redact_sensitive_text(text, source.url)

    ssh = ["ssh", *_SSH_OPTIONS, *_ssh_host_key_options(remote)]
    key_dir: Optional[str] = None
    key_lock: Optional[int] = None
    try:
        if isinstance(source.auth, SSHAuthData):
            try:
                key_dir, key_lock = _make_key_dir()
                ssh += ["-i", _write_key(key_dir, source.auth.private_key)]
            except OSError as e:
                raise GitCliLocalError(
                    128, f"fatal: cannot write the SSH key file: {e}"
                ) from None
        env["GIT_SSH_COMMAND"] = shlex.join(ssh)
        yield env, redact
    finally:
        if key_dir is not None:
            _remove_key_dir(Path(key_dir))
        if key_lock is not None:
            os.close(key_lock)


def _make_key_dir() -> Tuple[str, int]:
    """A new directory for one op's SSH key file, and an fd holding an flock on
    it, to be closed once the directory is removed: remove_dead_key_dirs
    removes only a key directory whose lock it can take.

    Raises:
        OSError: the directory cannot be made or locked.
    """
    path = tempfile.mkdtemp(
        prefix=f"{_KEY_DIR_PREFIX}{os.getpid()}-", dir=_key_dir_parent()
    )
    try:
        return path, _lock_key_dir(path)
    except BaseException:
        _remove_key_dir(Path(path))
        raise


def _lock_key_dir(path: str) -> int:
    """An fd holding an flock on the key directory ``path``.

    Raises:
        BlockingIOError: another fd holds it, in this process or any
            other.
        OSError: it cannot be opened or locked.
    """
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0))
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _key_dir_parent() -> str:
    """Where SSH key files go: /dev/shm (memory) where it is a writable
    directory, else the temp dir."""
    if os.path.isdir(_SHM) and os.access(_SHM, os.W_OK | os.X_OK):
        return _SHM
    return tempfile.gettempdir()


def _remove_key_dir(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.error(
            "Could not remove {path}, which holds SSH key material: {err!r}",
            path=path,
            err=e,
        )


def remove_dead_key_dirs() -> None:
    """Remove the SSH key directories of this user's processes that died before
    removing them: those whose lock (_make_key_dir) no process holds.

    The lock, not the pid in the name, says whether one is in use: after
    a container restart in the same pod, /dev/shm is still there and the
    new container's processes have the old ones' pids, and a container
    that shares /dev/shm cannot see this one's pids. A directory that
    holds no key file yet and is younger than _KEY_DIR_SETUP_SECONDS is
    left alone, lock or no lock: its op may not have taken the lock yet,
    and the sweep would take it first and remove the directory under the
    op. With no key in it, nothing secret waits for a later sweep. Never
    raises.
    """
    for parent in {_SHM, tempfile.gettempdir()}:
        try:
            with os.scandir(parent) as entries:
                found = [
                    e.path
                    for e in entries
                    if _KEY_DIR_RE.match(e.name)
                    and e.is_dir(follow_symlinks=False)
                    and e.stat(follow_symlinks=False).st_uid == os.getuid()
                ]
        except OSError:
            continue
        for path in found:
            if _key_dir_being_set_up(path):
                continue
            try:
                fd = _lock_key_dir(path)
            except (BlockingIOError, FileNotFoundError):
                continue  # an op under way holds it, or it is gone meanwhile
            except OSError as e:
                logger.warning(
                    "Could not lock {path} to tell whether a live process uses "
                    "it; leaving it: {err!r}",
                    path=path,
                    err=e,
                )
                continue
            try:
                _remove_key_dir(Path(path))
            finally:
                os.close(fd)


def _key_dir_being_set_up(path: str) -> bool:
    """Whether the key directory ``path`` holds no key file and was made less
    than _KEY_DIR_SETUP_SECONDS ago (False once it is gone)."""
    try:
        made = os.lstat(path).st_mtime
    except OSError:
        return False
    if os.path.lexists(os.path.join(path, _KEY_FILE)):
        return False
    return time.time() - made < _KEY_DIR_SETUP_SECONDS


def _write_key(key_dir: str, private_key: str) -> str:
    """Write ``private_key`` to a new 0600 file in ``key_dir``; its path.

    OpenSSH refuses a key whose last line has no newline, which libssh2
    takes, so one is added.
    """
    path = os.path.join(key_dir, _KEY_FILE)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(private_key if private_key.endswith("\n") else private_key + "\n")
    return path


# --- git's process group ------------------------------------------------------


# kill() of a process group whose members have all exited but are not reaped
# yet (zombies) fails with EPERM on macOS, where Linux signals them without
# error. An op's group holds git's processes only, all of this user, so on
# macOS EPERM says that no member of it is alive. (macOS is for development
# and CI; elsewhere EPERM is a member this process may not signal.)
EPERM_MEANS_NO_LIVE_MEMBER = sys.platform == "darwin"


def live_members(pgid: int) -> bool:
    """Whether process group ``pgid`` has a member that is not a zombie.

    A zombie is dead, and whether it is ever reaped is up to its parent
    (pid 1, once git that started it is gone), not to this op. Without
    /proc, or when it cannot be listed (EMFILE, say), any member counts,
    but on macOS kill() tells zombies apart.
    """
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return not EPERM_MEANS_NO_LIVE_MEMBER
    if not os.path.isdir("/proc/self"):
        return True
    try:
        names = os.listdir("/proc")
    except OSError:
        return True
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as f:
                fields = f.read().rpartition(")")[2].split()
        except OSError:
            continue  # gone meanwhile
        # After the command: state, ppid, pgrp, ...
        if len(fields) > 2 and fields[2] == str(pgid) and fields[0] not in "ZX":
            return True
    return False


class _PipeReader:
    """Reads one of sh's pipes to its end on the event loop.

    The read end (``fd``, this module's own) is the reader's once it is
    made (the caller's still, should making it raise), and is closed once
    read, or by ``close``; ``done`` then holds what was read, only its last
    ``keep`` bytes when given (``trimmed``: some came before them).
    """

    def __init__(self, fd: int, keep: Optional[int] = None) -> None:
        self._loop = asyncio.get_running_loop()
        self._fd: Optional[int] = fd
        self._keep = keep
        self._data = bytearray()
        self.trimmed = False
        self.done: "asyncio.Future[bytes]" = self._loop.create_future()
        os.set_blocking(fd, False)
        self._loop.add_reader(fd, self._read)

    def _read(self) -> None:
        assert self._fd is not None
        try:
            chunk = os.read(self._fd, 65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError as e:
            logger.warning("Could not read from the sh git runs under: {err!r}", err=e)
            chunk = b""
        if not chunk:
            self.close()
            return
        self._data += chunk
        if self._keep is not None and len(self._data) > self._keep:
            del self._data[: -self._keep]
            self.trimmed = True

    def close(self) -> None:
        """Stop reading and close the fd; ``done`` gets what was read so far,
        whatever the close raises."""
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            self._loop.remove_reader(fd)
            os.close(fd)
        finally:
            if not self.done.done():
                self.done.set_result(bytes(self._data))


class _Group:
    """One op's git, run under sh in a process group of its own, with what
    reads sh's pipes and reaps it.

    The group is gone once sh is reaped, both of its pipes are closed, and
    no member that is not a zombie is left: a member can close stderr and
    run on (the pipes alone would miss it), and a zombie keeps its group
    id in use while it waits for pid 1 to reap it (the group alone would
    wait for that).
    """

    def __init__(
        self,
        proc: "asyncio.subprocess.Process",
        stdin: int,
        status: _PipeReader,
        stderr: _PipeReader,
    ) -> None:
        self._proc = proc
        self._stdin: Optional[int] = stdin
        self._status = status
        self._stderr = stderr
        # asyncio has none of sh's pipes to wait for: this is done once sh is
        # reaped.
        self._reaped = asyncio.ensure_future(proc.wait())
        self._empty = False

    @property
    def pid(self) -> int:
        return self._proc.pid

    async def wait(self, timeout: Optional[float]) -> bool:
        """Wait up to ``timeout`` seconds (None: no limit); whether the group
        is gone."""
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout

        def _left() -> Optional[float]:
            return None if deadline is None else max(0.0, deadline - loop.time())

        done, _ = await asyncio.wait({self._reaped}, timeout=_left())
        if not done:
            return False
        # sh is reaped only once git is done (it outlives a stop's SIGTERM),
        # unless something killed sh alone. Its watchdog then kills what is
        # left of the group as its stdin closes. Not before: a member that
        # outlives sh holds sh's stderr, whose end would not come while the
        # watchdog lives.
        self.close_stdin()
        _, pending = await asyncio.wait(
            {self._status.done, self._stderr.done}, timeout=_left()
        )
        if pending:
            return False
        while not self._empty:
            if not live_members(self._proc.pid):
                self._empty = True
                break
            if deadline is not None and loop.time() >= deadline:
                return False
            await asyncio.sleep(_GROUP_POLL_SECONDS)
        return True

    def signal(self, sig: int) -> None:
        # The group's id is sh's pid, and its session's (start_new_session):
        # the kernel does not hand that id out again while any process of the
        # session is left, so until the group is seen empty it names this
        # group only.
        if self._empty:
            return
        try:
            os.killpg(self._proc.pid, sig)
        except ProcessLookupError:
            self._empty = True
        except PermissionError as e:
            if EPERM_MEANS_NO_LIVE_MEMBER:
                self._empty = True
                return
            # A member this process may not signal: the wait for the group
            # goes on by /proc (live_members).
            logger.warning(
                "Could not signal git's process group {pgid}: {err!r}",
                pgid=self._proc.pid,
                err=e,
            )

    def close_stdin(self) -> None:
        """Close sh's stdin: its watchdog, if it is still there, kills the
        group."""
        stdin, self._stdin = self._stdin, None
        if stdin is not None:
            os.close(stdin)

    def abandon(self) -> None:
        """The event loop is ending: close sh's pipes, and asyncio's transport
        for sh, while the loop still runs. Left to the garbage collector,
        they would be closed on a closed loop, which raises."""
        self.close_stdin()
        self._status.close()
        self._stderr.close()
        # asyncio's Process has no public close: its transport is private.
        self._proc._transport.close()  # type: ignore[attr-defined]

    def status(self) -> Optional[int]:
        """The exit status of git as sh reported it; None when sh reported none
        (it was killed first)."""
        try:
            return int(self._status.done.result().strip())
        except (asyncio.CancelledError, Exception):
            return None

    def stderr_tail(self, redact: Callable[[str], str]) -> str:
        """The end of git's stderr, ``redact``-ed before it is cut, so that no
        part of a secret the cut goes through is left, and without ssh's note
        of a host key it added to /dev/null."""
        try:
            raw = self._stderr.done.result()
        except (asyncio.CancelledError, Exception):
            return ""
        text = redact(raw.decode("utf-8", "replace"))
        if self._stderr.trimmed:
            # What was kept starts in the middle of a line, maybe of a secret
            # (git is given none with a newline): that line goes.
            text = text.partition("\n")[2]
        text = _SSH_HOST_KEY_ADDED.sub("", text)
        return text.strip()[-_STDERR_TAIL_CHARS:]


def _readers(status_read: int, stderr_read: int) -> Tuple[_PipeReader, _PipeReader]:
    """Readers of sh's stdout (git's status, as sh reports it) and stderr;
    should either fail to be made, both fds are closed."""
    try:
        status = _PipeReader(status_read)
    except BaseException:
        os.close(status_read)
        os.close(stderr_read)
        raise
    try:
        return status, _PipeReader(stderr_read, keep=_STDERR_TAIL_CHARS * 4)
    except BaseException:
        status.close()
        os.close(stderr_read)
        raise


async def _run_git(
    args: List[str],
    *,
    env: Dict[str, str],
    timeout: float,
    redact: Callable[[str], str],
    op: _Op,
) -> None:
    """Run ``git <args>`` in a process group of its own that holds the op's
    clone lock; return once git exited 0 and the group is gone, with the op
    still to finish.

    Every other outcome finishes the op (removes what git left, releases
    the lock, calls on_gone) once the group is gone, which for a stop
    (timeout, cancellation) or a member that outlives SIGKILL can be
    after this raised. The stop runs to its end even when the caller is
    cancelled again meanwhile.
    """
    git = shutil.which("git", path=env.get("PATH"))
    if git is None:
        await op.not_started()
        raise GitCliLocalError(127, "git not found on PATH")
    assert op.lock_fd is not None
    # sh's pipes are this module's own, not ones asyncio makes. Cancelled
    # before it has connected its pipes, asyncio leaves the ends it made
    # open (sh's stdin, which the watchdog reads: it would wait for good),
    # and, from Python 3.12, its give-up waits for every pipe it goes on
    # connecting to close: sh's stderr too, which git holds until the
    # watchdog ends it, which it does only once this process closes sh's
    # stdin after that give-up. With no pipe of asyncio's, the give-up
    # waits for sh alone.
    fds: List[int] = []
    try:
        for _ in range(3):
            fds.extend(os.pipe())
    except OSError as e:
        for fd in fds:
            os.close(fd)
        await op.not_started()
        raise GitCliLocalError(127, f"could not start git: {e}") from None
    watched, watching, status_read, status_write, stderr_read, stderr_write = fds
    # sh's pipes are read from before sh starts: nothing is left to fail
    # between its start and its group's stop.
    try:
        status, stderr = _readers(status_read, stderr_read)
    except BaseException as e:
        for fd in (watched, watching, status_write, stderr_write):
            os.close(fd)
        await op.not_started()
        if isinstance(e, OSError):
            raise GitCliLocalError(127, f"could not start git: {e}") from None
        raise
    # From here on sh may be running whatever the start ends in: the group's
    # id is not known then, so the clone's lock, which every member holds,
    # says when it is gone.
    try:
        proc = await asyncio.create_subprocess_exec(
            _SH,
            "-c",
            _STATUS_SCRIPT,
            "sh",
            git,
            *args,
            stdin=watched,
            stdout=status_write,
            stderr=stderr_write,
            env=env,
            start_new_session=True,
            pass_fds=(op.lock_fd,),
        )
    except BaseException as e:
        # asyncio, giving up on a start, kills sh only; sh's watchdog, if sh
        # got that far, kills the rest of the group as its stdin closes.
        os.close(watching)
        status.close()
        stderr.close()
        _keep(op.finish_once_unlocked())
        if isinstance(e, OSError):
            raise GitCliLocalError(127, redact(f"could not start git: {e}")) from None
        raise
    finally:
        for fd in (watched, status_write, stderr_write):
            os.close(fd)
    group = _Group(proc, watching, status, stderr)
    limit = _timeout_or_none(timeout)
    try:
        finished = await group.wait(limit)
    except BaseException:
        await asyncio.shield(_background_stop(group, op))
        raise
    if not finished:
        await asyncio.shield(_background_stop(group, op))
        raise GitCliTimeoutError(f"git {op.what} exceeded {limit}s")
    status = group.status()
    if status == 0:
        return
    # A git killed by a signal OPAL did not send (an OOM kill), or whose sh
    # was, removed none of its locks: they are removed before the lock goes.
    await op.finish(succeeded=False, status=status)
    if status is None:
        raise GitCliError(
            -1,
            "the sh git ran under was killed before it reported git's exit "
            f"status. {group.stderr_tail(redact)}".strip(),
        )
    raise GitCliError(status, group.stderr_tail(redact))


def _background_stop(group: _Group, op: _Op) -> "asyncio.Future[bool]":
    """Stop the group on a task of its own, referenced until it is done; a
    future of whether the group was gone within the stop, done once the op is
    finished (True), or once the stop is over with a member that outlived
    SIGKILL (False), when the task finishes the op after it exits."""
    stopped: "asyncio.Future[bool]" = asyncio.get_running_loop().create_future()
    _keep(_stop_then_finish(group, op, stopped))
    return stopped


def _keep(coro) -> "asyncio.Future":
    task = asyncio.ensure_future(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


async def _stop_then_finish(
    group: _Group, op: _Op, stopped: "asyncio.Future[bool]"
) -> None:
    try:
        gone = await _stop(group, op.what, kill_grace_seconds())
        if not gone:
            stopped.set_result(False)
            await group.wait(None)
            logger.warning(
                "git {what} (pid {pid}) has exited at last", what=op.what, pid=group.pid
            )
        try:
            await op.finish(succeeded=False, status=None)
        finally:
            if not stopped.done():
                stopped.set_result(True)
    except asyncio.CancelledError:
        # The event loop is ending, and will not run this to its end: no
        # waiting, then. SIGKILL now, and leave the op recorded in its lock
        # file for the next op on the clone to clean up after.
        group.signal(signal.SIGKILL)
        group.abandon()
        op.abandon()
        if not stopped.done():
            stopped.cancel()
        raise
    except Exception as e:
        # Anything else that broke the stop would leave the op, its clone's
        # lock and its caller waiting for good: SIGKILL the group (and close
        # sh's stdin, which nothing else closes now) and finish the op
        # without waiting for the group.
        logger.error(
            "Stopping git {what} (pid {pid}) failed: {err!r}; sending SIGKILL "
            "and finishing the op without waiting for its process group",
            what=op.what,
            pid=group.pid,
            err=e,
        )
        try:
            group.signal(signal.SIGKILL)
            group.close_stdin()
            await op.finish(succeeded=False, status=None)
        finally:
            if not stopped.done():
                stopped.set_result(True)


async def _stop(group: _Group, what: str, grace: float) -> bool:
    """SIGTERM the group, then SIGKILL it if it is still there after ``grace``
    seconds (``grace`` 0: SIGKILL at once); whether it is gone within
    KILL_WAIT_SECONDS of the SIGKILL."""
    if grace > 0:
        group.signal(signal.SIGTERM)
        if await group.wait(grace):
            return True
        logger.warning(
            "git {what} (pid {pid}) still running {grace}s after SIGTERM; "
            "sending SIGKILL",
            what=what,
            pid=group.pid,
            grace=grace,
        )
    group.signal(signal.SIGKILL)
    if await group.wait(KILL_WAIT_SECONDS):
        return True
    logger.error(
        "git {what} (pid {pid}) still running {secs}s after SIGKILL (stuck in "
        "uninterruptible I/O?); its clone is left alone until it exits",
        what=what,
        pid=group.pid,
        secs=KILL_WAIT_SECONDS,
    )
    return False
