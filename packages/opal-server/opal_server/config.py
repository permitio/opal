import os
import pathlib
from enum import Enum

from opal_common.authentication.types import EncryptionKeyFormat
from opal_common.confi import Confi
from opal_common.schemas.data import DEFAULT_DATA_TOPIC, ServerDataSourceConfig
from opal_common.schemas.webhook import GitWebhookRequestParams

confi = Confi(prefix="OPAL_")


class PolicySourceTypes(str, Enum):
    Git = "GIT"
    Api = "API"


class PolicyBundleServerType(str, Enum):
    HTTP = "HTTP"
    AWS_S3 = "AWS-S3"


class ServerRole(str, Enum):
    Primary = "primary"
    Secondary = "secondary"


class OpalServerConfig(Confi):
    # ws server
    OPAL_WS_LOCAL_URL = confi.str(
        "WS_LOCAL_URL",
        "ws://localhost:7002/ws",
        description="The local WebSocket URL for OPAL",
    )
    OPAL_WS_TOKEN = confi.str(
        "WS_TOKEN",
        "THIS_IS_A_DEV_SECRET",
        description="The WebSocket token for OPAL",
        sensitive=True,
    )
    CLIENT_LOAD_LIMIT_NOTATION = confi.str(
        "CLIENT_LOAD_LIMIT_NOTATION",
        None,
        description="If supplied, rate limit would be enforced on server's websocket endpoint. "
        + "Format is `limits`-style notation (e.g '10 per second'), "
        + "see link: https://limits.readthedocs.io/en/stable/quickstart.html#rate-limit-string-notation",
    )
    # The URL for the backbone pub/sub server (e.g. Postgres, Kfaka, Redis) @see
    BROADCAST_URI = confi.str(
        "BROADCAST_URI", None, description="The URL for the backbone pub/sub server"
    )
    # The name to be used for segmentation in the backbone pub/sub (e.g. the Kafka topic)
    BROADCAST_CHANNEL_NAME = confi.str(
        "BROADCAST_CHANNEL_NAME",
        "EventNotifier",
        description="The name to be used for segmentation in the backbone pub/sub",
    )
    BROADCAST_RECONNECT_ENABLED = confi.bool(
        "BROADCAST_RECONNECT_ENABLED",
        True,
        description="Reconnect the broadcaster reader on a backbone disconnect instead "
        "of dropping all client connections. Set to False to revert to the legacy "
        "(non-reconnecting) broadcaster.",
    )
    BROADCAST_RECONNECT_MAX_RETRIES = confi.int(
        "BROADCAST_RECONNECT_MAX_RETRIES",
        0,
        description="Maximum consecutive broadcaster reconnect attempts before giving "
        "up and letting the worker restart (0 = retry forever).",
    )
    BROADCAST_RECONNECT_BACKOFF_MIN_SECONDS = confi.float(
        "BROADCAST_RECONNECT_BACKOFF_MIN_SECONDS",
        0.5,
        description="Minimum backoff in seconds between broadcaster reconnect attempts.",
    )
    BROADCAST_RECONNECT_BACKOFF_MAX_SECONDS = confi.float(
        "BROADCAST_RECONNECT_BACKOFF_MAX_SECONDS",
        30.0,
        description="Maximum backoff in seconds between broadcaster reconnect attempts.",
    )
    BROADCAST_REPLAY_BUFFER_SIZE = confi.int(
        "BROADCAST_REPLAY_BUFFER_SIZE",
        10000,
        description="Max number of outbound broadcasts buffered while the backbone is "
        "down and replayed on reconnect (0 disables buffering). On overflow the oldest "
        "buffered broadcasts are dropped; the resync on reconnect still reconciles clients.",
    )
    BROADCAST_RESYNC_ON_RECONNECT = confi.bool(
        "BROADCAST_RESYNC_ON_RECONNECT",
        True,
        description="After a backbone gap that may have lost updates, force this "
        "worker's connected clients to reconnect so they re-fetch full policy + data "
        "state (guarantees cross-instance consistency). With scopes on, the "
        "leader also runs one sync pass of every scope, so a refresh published "
        "during the gap is not lost (a source in backoff waits for its delay).",
    )
    BROADCAST_RESYNC_SETTLE_SECONDS = confi.float(
        "BROADCAST_RESYNC_SETTLE_SECONDS",
        2.0,
        description="Grace period after a broadcaster reconnect before replaying "
        "buffered broadcasts and resyncing clients, to let peer servers re-subscribe.",
    )
    BROADCAST_HEALTHCHECK_ENABLED = confi.bool(
        "BROADCAST_HEALTHCHECK_ENABLED",
        True,
        description="Make /healthcheck (readiness) and /healthz/live (liveness) "
        "reflect the broadcaster reader's health, so a k8s probe can route away "
        "from or restart a worker whose reader is wedged or gave up while clients "
        "depend on it; in scopes mode /healthcheck also waits for the worker's own "
        "backbone subscription. Set to False to drop these broadcaster checks "
        "from both routes.",
    )
    BROADCAST_FREEZE_ON_DISCONNECT = confi.bool(
        "BROADCAST_FREEZE_ON_DISCONNECT",
        True,
        description="During a broadcaster backbone gap, freeze client-facing publishes on "
        "every worker instead of applying them locally — so a write that cannot fan out to "
        "the whole fleet is never served by just one worker (fleet consistency over "
        "freshness). Recovery is the reconnect resync: clients re-fetch their configured "
        "data sources and policy, so updates covered by those are reconciled; one-off "
        "updates outside them (inline data payloads, ad-hoc fetch URLs) are DROPPED by a "
        "freeze, not deferred. Internal coordination topics (statistics, keepalive, the git "
        "webhook trigger) are exempt and keep the deliver-locally + buffer-for-replay "
        "behavior. Engages only with BROADCAST_RECONNECT_ENABLED (without the reconnecting "
        "broadcaster there is no gap signal, so the flag is a no-op) and requires "
        "BROADCAST_RESYNC_ON_RECONNECT (if the resync is disabled, freezing is refused "
        "with a warning). Set to False for "
        "the previous behavior, where the receiving worker's own clients update immediately "
        "and peers only after reconnect.",
    )

    # server security
    AUTH_PRIVATE_KEY_FORMAT = confi.enum(
        "AUTH_PRIVATE_KEY_FORMAT",
        EncryptionKeyFormat,
        EncryptionKeyFormat.pem,
        description="The format of the private key for authentication",
    )
    AUTH_PRIVATE_KEY_PASSPHRASE = confi.str(
        "AUTH_PRIVATE_KEY_PASSPHRASE",
        None,
        description="The passphrase for the private key",
        sensitive=True,
    )

    AUTH_PRIVATE_KEY = confi.delay(
        lambda AUTH_PRIVATE_KEY_FORMAT=None, AUTH_PRIVATE_KEY_PASSPHRASE="": (
            confi.private_key(
                "AUTH_PRIVATE_KEY",
                default=None,
                key_format=AUTH_PRIVATE_KEY_FORMAT,
                passphrase=AUTH_PRIVATE_KEY_PASSPHRASE,
                description="The private key for authentication",
                sensitive=True,
            )
        )
    )

    AUTH_JWKS_URL = confi.str(
        "AUTH_JWKS_URL",
        "/.well-known/jwks.json",
        description="The URL for the JSON Web Key Set (JWKS)",
    )
    AUTH_JWKS_STATIC_DIR = confi.str(
        "AUTH_JWKS_STATIC_DIR",
        os.path.join(os.getcwd(), "jwks_dir"),
        description="The directory for static JWKS files",
    )

    AUTH_MASTER_TOKEN = confi.str(
        "AUTH_MASTER_TOKEN",
        None,
        description="The master token for authentication",
        sensitive=True,
    )

    # policy source watcher
    POLICY_SOURCE_TYPE = confi.enum(
        "POLICY_SOURCE_TYPE",
        PolicySourceTypes,
        PolicySourceTypes.Git,
        description="Set your policy source can be GIT / API",
    )
    POLICY_REPO_URL = confi.str(
        "POLICY_REPO_URL",
        None,
        description="Set your remote repo URL e.g:https://github.com/permitio/opal-example-policy-repo.git\
        , relevant only on GIT source type",
    )
    POLICY_BUNDLE_URL = confi.str(
        "POLICY_BUNDLE_URL",
        None,
        description="Set your API bundle URL, relevant only on API source type",
    )
    POLICY_REPO_CLONE_PATH = confi.str(
        "POLICY_REPO_CLONE_PATH",
        os.path.join(os.getcwd(), "regoclone"),
        description="Base path to create local git folder inside it that manage policy change",
    )
    POLICY_REPO_CLONE_FOLDER_PREFIX = confi.str(
        "POLICY_REPO_CLONE_FOLDER_PREFIX",
        "opal_repo_clone",
        description="Prefix for the local git folder",
    )
    POLICY_REPO_REUSE_CLONE_PATH = confi.bool(
        "POLICY_REPO_REUSE_CLONE_PATH",
        False,
        description="Set if OPAL server should use a fixed clone path (and reuse if it already exists) instead of randomizing its suffix on each run",
    )
    POLICY_REPO_MAIN_BRANCH = confi.str(
        "POLICY_REPO_MAIN_BRANCH",
        "master",
        description="The main branch of the policy repository",
    )
    POLICY_REPO_SSH_KEY = confi.str(
        "POLICY_REPO_SSH_KEY",
        None,
        description="The SSH key for the policy repository",
        sensitive=True,
    )
    POLICY_REPO_MANIFEST_PATH = confi.str(
        "POLICY_REPO_MANIFEST_PATH",
        "",
        description="Path of the directory holding the '.manifest' file (new fashion), or of the manifest file itself (old fashion). Repo's root is used by default",
    )
    POLICY_REPO_CLONE_TIMEOUT = confi.int(
        "POLICY_REPO_CLONE_TIMEOUT",
        0,
        description="The timeout for cloning the policy repository (0 means wait forever)",
    )
    SCOPES_GIT_FETCH_TIMEOUT = confi.float(
        "SCOPES_GIT_FETCH_TIMEOUT",
        120.0,
        description="Timeout in seconds for a single scope git fetch, and with "
        "SCOPES_GIT_FETCH_WITH_CLI off for a clone too: the op is logged and "
        "skipped, retried next cycle, so one unreachable repo never blocks boot "
        "or other scopes (0 = no timeout). With SCOPES_GIT_FETCH_WITH_CLI on "
        "(the default) it is a HARD timeout: git is stopped at the timeout (see "
        "SCOPES_GIT_CLI_KILL_GRACE), and a clone has SCOPES_GIT_CLONE_TIMEOUT "
        "instead. With it off it is a SOFT timeout: the awaiting operation is "
        "abandoned (the event loop and the sync pass move on), but the "
        "underlying libgit2 call keeps running on its own thread, and libgit2 "
        "sets no socket/server read timeout, so a black-holed remote can keep "
        "that thread — and the source's in-flight marker — alive for the life "
        "of the process (that source is then skipped until it recovers or the "
        "process restarts); SCOPES_GIT_MAX_ZOMBIES bounds how many such threads "
        "accumulate. A sync that is not part of a sync pass (a refresh, a PUT "
        "/scopes, the sync a policy bundle request asks for) and finds a git op "
        "of this process still running on its clone (a libgit2 op past its "
        "timeout, or a git command-line op until git has been stopped) waits up "
        "to that op's own timeout for it to end (this one for a fetch, "
        "SCOPES_GIT_CLONE_TIMEOUT for a git command-line clone), then syncs once "
        "more (with 0, it does not wait); a pass's sync skips that clone, and the "
        "next pass syncs it. "
        "No git op, and no sync waiting for one, delays the scopes leader's heartbeat "
        "(/healthz/live), which runs on a task of its own: with "
        "SCOPES_GIT_FETCH_WITH_CLI on, an op holds it only while it is still awaited "
        "40 seconds past its own timeout (this one, or SCOPES_GIT_CLONE_TIMEOUT for a "
        "clone) plus SCOPES_GIT_CLI_KILL_GRACE, by when git has been stopped, and an "
        "op with no timeout never holds it.",
    )
    SCOPES_GIT_CLONE_TIMEOUT = confi.float(
        "SCOPES_GIT_CLONE_TIMEOUT",
        None,
        description="With SCOPES_GIT_FETCH_WITH_CLI on: the hard timeout in "
        "seconds of a scope clone, which downloads the whole repository and "
        "takes longer than a fetch. git is stopped at it as a fetch is at "
        "SCOPES_GIT_FETCH_TIMEOUT (see SCOPES_GIT_CLI_KILL_GRACE), and a clone "
        "stopped there never lands: the next sync starts it over. When unset "
        "(the default), 5 times SCOPES_GIT_FETCH_TIMEOUT; 0 or less means no "
        "limit. Size it from a measured clone of the largest repository, with "
        "room to spare. The pre-fork scope preload waits for each clone, so a "
        "start can take this long, plus SCOPES_GIT_CLI_KILL_GRACE, when a "
        "remote stalls a clone: size a startup probe for it. The server does "
        "not start when it is below "
        "SCOPES_GIT_FETCH_TIMEOUT (no limit counting as the highest). With "
        "SCOPES_GIT_FETCH_WITH_CLI off, a libgit2 clone has "
        "SCOPES_GIT_FETCH_TIMEOUT. "
        "A clone that runs up to this timeout never fails /healthz/live: see "
        "SCOPES_GIT_FETCH_TIMEOUT.",
    )
    SCOPES_GIT_FETCH_WITH_CLI = confi.bool(
        "SCOPES_GIT_FETCH_WITH_CLI",
        True,
        description="Whether scope fetches and clones run the git command line "
        "(git fetch; the default) or, when false, libgit2. With the git command "
        "line each repository has one clone (see SCOPES_REPO_CLONES_SHARDS). "
        "What it needs is checked at start only in scopes mode (a policy "
        "repository tracked outside scopes mode, with POLICY_SOURCE_TYPE GIT, "
        "the default, runs git too). A libgit2 fetch runs on a thread that "
        "cannot be stopped, so one that hangs keeps its clone from syncing until "
        "it returns or the process restarts. With this on each op runs git in a "
        "process group of its own, and SCOPES_GIT_FETCH_TIMEOUT "
        "(SCOPES_GIT_CLONE_TIMEOUT for a clone) is hard: at the "
        "timeout the group gets SIGTERM, then SIGKILL SCOPES_GIT_CLI_KILL_GRACE "
        "seconds later, the lock files and partial pack git left in the clone "
        "are removed, and the next sync fetches the clone again. The group also "
        "ends itself when the server process that started it dies. Each op holds "
        "a lock on its clone (the file `.SOURCE_ID.lock` beside it) that git "
        "and the git processes it starts inherit, so no other op, repack or "
        "cleanup touches the clone while any of them lives; a sync that finds a "
        "clone locked skips it and counts opal_server.scopes.git_op_skipped "
        "(reason clone_busy). The lock is an flock: where the filesystem holding "
        "the clones refuses one, every fetch and clone fails with reason `local`. "
        "What an op that ended early left in its clone is "
        "removed by the next op on that clone, and by the pre-fork scope preload "
        "for every clone, with this on or off. Remote timeouts and failures are "
        "logged, counted and backed off as libgit2's are; failures on the "
        "server's own side (no git, a clone that cannot be set up, an "
        "unreadable SCOPES_GIT_SSH_KNOWN_HOSTS) are logged at ERROR and counted "
        "with reason `local`, without backoff. A source whose URL or "
        "credentials cannot be given to git without a credential on its "
        "command line or in what it prints is logged and counted the same "
        "way, and backed off as well, since only a change of the source fixes "
        "it. A new "
        "clone is fetched into a directory beside its final path and renamed "
        "into place once complete. A clone keeps what the scopes fetcher reads "
        "from a libgit2 clone (the same remote, its `refs/remotes/<remote>/*` "
        "refs, a FETCH_HEAD rewritten only by a fetch that succeeded), so this "
        "can be switched either way without cloning again, and bundles are "
        "built from it as before; a clone made by git has no checkout, which "
        "nothing reads. Fetches skip tags and prune when SCOPES_GIT_FETCH_PRUNE "
        "is on. A fetch asks the remote only for the branches its syncs need, "
        "each as one protocol v2 ref prefix, so the server lists and sends only "
        "those: a refresh, a PUT /scopes that changes a scope's source or branch, "
        "or a sync for a branch the clone lacks asks for its scope's branch; the "
        "syncs of a clone that wait for its lock while its fetch runs share the "
        "next fetch, which asks for the branches of those still waiting; a sync "
        "pass (at start, after a backbone gap, POST /scopes/refresh, the "
        "periodic one) asks for every branch the stored scopes track on the "
        "clone, or for every branch above "
        "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES. A branch is asked for as a "
        "pattern, `+refs/heads/BRANCH*:refs/remotes/<remote>/BRANCH*`: one the "
        "remote does not have fails nothing, and the branches whose names start "
        "with it come too (`release` brings `release-2`). A name that cannot be "
        "a git ref, or whose `refs/remotes/<remote>/BRANCH` is 1,024 bytes or "
        "more, is never asked for. A fetch stands in for another sync's fetch of "
        "a branch only if it asked for that branch, started after that sync was "
        "asked for, and reached the remote: one that failed there makes each "
        "sync it stood for, outside a pass, fetch once more when the source's "
        "backoff allows (if that is within 300 seconds), and one that never "
        "reached it (the clone busy, a failure on this server's side) stands in "
        "for none. A clone that missed a refresh of one scope catches up at that "
        "scope's next refresh or the next sync pass, not at a fetch for another "
        "scope. FETCH_HEAD's age is that of the clone's last fetch or clone that "
        "succeeded, whatever branches it asked for; when each branch was last "
        "fetched is the mtime of a file in the clone's .git/opal-fetched, set to "
        "the start of the fetch, one for a fetch of it that succeeded and one for "
        "one that reached the remote and failed (ALL for a clone or a fetch of "
        "every branch, which also removes the older files, FAILED for a fetch of "
        "every branch that failed). git "
        "reads neither the system's nor the user's git config, which "
        "libgit2 does read, so whatever else they set (a url.insteadOf, say) is "
        "lost with this on; only their safe.directory is given to git, which "
        "git 2.38 or later honours. As libgit2 does, git runs no hooks, reads "
        "no ~/.netrc, speaks only http, https, ssh, git and file, and uses no "
        "proxy; the CA certificates of SSL_CERT_FILE and "
        "SSL_CERT_DIR reach it as GIT_SSL_CAINFO and GIT_SSL_CAPATH. "
        "Credentials reach git through its environment, for http(s) through a "
        "credential helper that answers only for the source's own host, over "
        "the source's protocol or, for an http source, https (where a "
        "redirect to https takes git), or, for "
        "an SSH key, a file only the server's user can read, removed when the "
        "op ends; never through its command line. git speaks protocol v2, "
        "whatever a clone's own config says, and ssh gives up on a connect "
        "after 30 seconds and on a link the server stays silent on after about "
        "a minute (4 keepalives, 15 seconds apart, unanswered), with an error "
        "of its own rather than at the timeout. Each op starts git from the "
        "server process with Python's subprocess module (vfork on Linux), "
        "not with the event loop's own process start (uvloop's forks the "
        "whole process and runs its at-fork hooks), so the start does not "
        "grow with the memory the server holds and runs none of the process's "
        "at-fork hooks. Needs git 2.32 or later on PATH, "
        "/bin/sh (git runs under it, which reports git's exit status), and "
        "ssh for SSH sources; the official "
        "images have all three, and the server does not "
        "start without git 2.32 or /bin/sh. "
        "Unlike libgit2, ssh needs the server's uid to have an entry in the "
        "user database (/etc/passwd): under a uid with none, an arbitrary one "
        "given at runtime say, every SSH fetch fails, which the server logs at "
        "ERROR at start; add an entry, or use nss_wrapper, whose LD_PRELOAD "
        "and `NSS_WRAPPER_*` variables git and ssh are given. "
        "ssh from OpenSSH 8.8 on, which the official images have, refuses "
        "ssh-rsa (SHA-1) signatures: a git server that offers only an ssh-rsa "
        "host key, which libgit2 accepts, works with this off and fails with it "
        "on. One that takes only ssh-rsa signatures of the user's RSA key fails "
        "with this on, and with it off too unless it lists only ssh-rsa in its "
        "server-sig-algs (as the sshd of OpenSSH 10 does). "
        "SSH key files go to /dev/shm where it is writable, else to the temp "
        "dir (TMPDIR); the server does not start when that path holds % or $, "
        "which ssh would expand. "
        "SSH host keys: see SCOPES_GIT_SSH_KNOWN_HOSTS.",
    )
    SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES = confi.int(
        "SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES",
        1000,
        description="With SCOPES_GIT_FETCH_WITH_CLI on: the most branches a "
        "scope fetch names (see SCOPES_GIT_FETCH_WITH_CLI); a fetch that needs "
        "more fetches every branch, the clone's whole refspec, instead. git "
        "matches each name against every branch the server lists (and, pruning, "
        "every branch the clone holds): on a repository with 63,000 branches, a "
        "fetch of 1,000 names took no longer than one of every branch without "
        "SCOPES_GIT_FETCH_PRUNE, and a longer list took longer. It also bounds "
        "git's command line, where the names go. 0: every fetch fetches every "
        "branch, as before 0.10. The server does not start when it is "
        "negative. Ignored with SCOPES_GIT_FETCH_WITH_CLI off: libgit2 fetches "
        "every branch.",
    )
    SCOPES_GIT_SSH_KNOWN_HOSTS = confi.str(
        "SCOPES_GIT_SSH_KNOWN_HOSTS",
        None,
        description="The path of a known_hosts file to verify the git host's SSH "
        "key against, with either fetch backend. When set, a scope fetch or "
        "clone over SSH goes ahead only if the host's key is in this file (ssh's "
        "StrictHostKeyChecking=yes), and the file is never written to. Its lines "
        "are OpenSSH known_hosts lines; a host on a port other than 22 is "
        "written `[host]:port`. A relative path is resolved against the server's "
        "working directory on each op. When unset (the default), host keys are "
        "trusted on first use: the first SSH fetch or clone records the host's "
        "key, and a later one refuses a different key. The git command line "
        "records, beside each clone (git_sources/.SOURCE_ID.known_hosts in "
        "BASE_DIR), the key of the type ssh negotiated; libgit2 records, once "
        "per host and port in one file for all clones, each key ssh-keyscan "
        "(which it then needs on PATH) reads from the host, in "
        "git_sources/.libgit2-home/.ssh/known_hosts (libgit2's home is set to "
        "git_sources/.libgit2-home, or, with this set, to a directory there "
        "whose known_hosts links to this file). libgit2 looks a host up as the "
        "source's URL writes it, capitals included, in this file too. A clone "
        "made again keeps its record. A refused key fails the op with reason "
        "`host_key`, backs the source off, and logs an ERROR that names the "
        "file: when a host did change its key, delete that file (with libgit2, "
        "the host's lines in it) on each server, or replace the pod when "
        "BASE_DIR is on an emptyDir, then refresh the scope (POST "
        "/scopes/:scope_id/refresh, or a PUT of it), whose fetch records the new "
        "key: until then the source stays backed off. In scopes mode the server "
        "does not start when "
        "this names no readable file or its path holds whitespace, % or $, a "
        "quote or a backslash (ssh would read the path as a list, expand it, or "
        "take it as quoting); nor, with this unset and SCOPES_GIT_FETCH_WITH_CLI "
        "on, when BASE_DIR's git_sources path holds those; nor, with "
        "SCOPES_GIT_FETCH_WITH_CLI off, when that path holds : or $ (libgit2 "
        "reads its home as a list of directories, and expands $PATH there). A "
        "file that becomes unreadable later fails each SSH fetch at once "
        "(counted with reason `local`).",
    )
    SCOPES_GIT_CLI_KILL_GRACE = confi.float(
        "SCOPES_GIT_CLI_KILL_GRACE",
        5.0,
        description="With SCOPES_GIT_FETCH_WITH_CLI on: seconds a git fetch or "
        "clone that ran past its timeout (SCOPES_GIT_FETCH_TIMEOUT, or "
        "SCOPES_GIT_CLONE_TIMEOUT for a clone) gets to exit on SIGTERM, "
        "which lets git remove its own lock files and temporary pack, before its "
        "process group gets SIGKILL. OPAL then waits up to 10 seconds more for "
        "the group to exit, and once it has, removes what git left in the "
        "clone (for a clone, its partial directory) before the op ends. The "
        "timeout counts from git's start, after the op has taken the clone's "
        "lock and removed what an earlier op left, so an op ends at most this "
        "plus 10 seconds, plus that removal, past its timeout. A git stuck in "
        "uninterruptible I/O even after SIGKILL keeps "
        "its clone from being synced until it exits, as a hung libgit2 fetch "
        "does. 0 sends SIGKILL at once. With SCOPES_GIT_FETCH_WITH_CLI on, the "
        "server does not start when this is negative, nan or inf.",
    )
    SCOPES_GIT_FETCH_PRUNE = confi.bool(
        "SCOPES_GIT_FETCH_PRUNE",
        False,
        description="Whether a scope fetch prunes: a branch deleted on the remote "
        "then leaves the clone, so a scope naming it misses instead of being "
        "served the deleted branch's last head. Off by default: a pruned fetch "
        "compares every local and remote ref, which on a clone with tens of "
        "thousands of branches adds seconds per fetch under the lock every scope "
        "on that clone shares. libgit2 (SCOPES_GIT_FETCH_WITH_CLI off) removes "
        "a pruned ref kept in a file of its own in well under a millisecond, but "
        "rewrites the whole packed-refs file for each ref it prunes from it, and "
        "that file grows with the repository's branches: about 13 ms per ref on "
        "a clone of a repository with 63,000 branches (79 seconds for 6,000 "
        "deleted refs). With this on and "
        "SCOPES_GIT_FETCH_WITH_CLI off, the repack therefore leaves a clone's "
        "refs in files of their own instead of packing them (see "
        "SCOPES_GIT_REPACK_PACK_LIMIT); a clone whose refs are packed already "
        "(one made with SCOPES_GIT_FETCH_WITH_CLI on) keeps them packed, and its "
        "fetches pay that cost. Only `refs/remotes/<remote>/*` are pruned; the "
        "scopes' `refs/heads/scopes/*` stay. A git command-line fetch that asks "
        "for some branches (see SCOPES_GIT_FETCH_WITH_CLI) prunes only the refs "
        "of those branches, and of the branches whose names start with one of "
        "them: a branch deleted on the remote leaves the clone at the next fetch "
        "that asks for it (its scope's refresh, or a sync pass), and one that no "
        "scope tracks only at a fetch of every branch.",
    )
    SCOPES_GIT_MAX_WORKERS = confi.int(
        "SCOPES_GIT_MAX_WORKERS",
        # Worst-case OS-thread count during an outage is this limit plus the
        # number of lingering timed-out ("zombie") libgit2 ops: a timed-out
        # libgit2 op releases its concurrency slot but keeps a daemon thread
        # running on its own. SCOPES_GIT_MAX_ZOMBIES bounds that tail.
        10,
        description="Maximum number of concurrent scope git operations. It bounds "
        "phase 1 (the network clone/fetch of each distinct repo) AND phase 2 (the "
        "local change-check of scopes that reuse an already-cloned repo), so it "
        "sets how many clones a sync pass syncs at once in either phase. In "
        "phase 1 that is one scope per clone. In phase 2 a clone's slot syncs "
        "up to 8 of its scopes at once, in lanes of their own: they read their "
        "records from the store side by side, and take the clone's sync lock one "
        "at a time for the change-check, so up to 8 times this many scopes are in "
        "flight, while each clone's git work still runs one scope at a time. "
        "Those reads each take a connection from the leader worker's Redis "
        "connection pool, which therefore grows to about 8 times this many "
        "connections at a pass's peak, and does not shrink. With "
        "SCOPES_GIT_FETCH_WITH_CLI off, a timed-out operation stops counting "
        "against this limit, so one hung remote does not "
        "hold a concurrency slot — its lingering daemon thread persists on its own "
        "(a black-holed remote's can persist for the life of the process). That "
        "tail is bounded by SCOPES_GIT_MAX_ZOMBIES, which is a GLOBAL ceiling: "
        "read its description, because at that ceiling new git ops are refused "
        "for every scope, healthy ones included. With SCOPES_GIT_FETCH_WITH_CLI "
        "on, a timed-out fetch leaves no thread behind, and holds its slot until "
        "git is stopped: up to SCOPES_GIT_CLI_KILL_GRACE plus 10 seconds, plus "
        "the removal of what git left, past the timeout. A clone gives its slot "
        "back once it has run SCOPES_GIT_FETCH_TIMEOUT and runs on outside this "
        "limit, up to SCOPES_GIT_CLONE_TIMEOUT, still counted against "
        "SCOPES_GIT_MAX_ZOMBIES: clones of remotes that never answer hold the "
        "slots no longer than fetches do.",
    )
    SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT = confi.float(
        "SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT",
        10.0,
        description="Max seconds the pre-fork scope preload waits for in-flight git "
        "ops to finish before tearing down and forking workers. Ops still lingering "
        "past this bound are left running on their daemon threads and their cached "
        "handles are left unfreed by the pre-fork cache reset, avoiding a use-after-free "
        "(0 = don't wait). With SCOPES_GIT_FETCH_WITH_CLI on, the preload's event "
        "loop also waits up to this long for git command-line ops still being "
        "stopped; those not done by then get SIGKILL as the loop ends, their "
        "clones stay recorded as unfinished, and the next op on each clone "
        "removes what git left. With libgit2 (opt-in, SCOPES_GIT_FETCH_WITH_CLI "
        "off), a libgit2 op still running when this wait ends keeps the pack "
        "files it has open, in the gunicorn master and in every worker forked "
        "from it: a pack a later repack deletes keeps its disk space until "
        "the server restarts. With the git command line no such op is left.",
    )
    SCOPES_GIT_RECLONE_HUNG_ON_START = confi.bool(
        "SCOPES_GIT_RECLONE_HUNG_ON_START",
        False,
        description="Whether a server start clones again the scope clones on which a git "
        "op was still hung when its server process ended. A libgit2 fetch or "
        "clone that runs past SCOPES_GIT_FETCH_TIMEOUT keeps running on its "
        "daemon thread, and the clone is not fetched again while it lasts; a "
        "git command-line one (SCOPES_GIT_FETCH_WITH_CLI) is stopped at its "
        "timeout (SCOPES_GIT_CLONE_TIMEOUT for a clone), which it can outlive "
        "only stuck in uninterruptible I/O. With this on (and "
        "SCOPES_GIT_FETCH_TIMEOUT positive), such an op writes a "
        "marker file of its own, with a unique name, in a directory beside "
        "the clone (git_sources/SOURCE_ID.hung/, SOURCE_ID being the clone's "
        "directory name) and removes it when it returns. A marker whose "
        "process ended first (a container restart, or a worker killed mid-op) "
        "stays until a fetch or clone of that source succeeds within its "
        "timeout, which removes them all; a fetch that fails quickly (revoked "
        "credentials, a deleted repository) or succeeds only after its "
        "timeout does not remove it. With this off a start removes them all. "
        "A container restarted while an op was still hung (by an "
        "orchestrator's health check, say) keeps its clones on its volume and "
        "would otherwise go back to that clone, while a new pod (empty "
        "volume) clones fresh. The pre-fork scope preload, which "
        "scripts/gunicorn_conf.py runs in the gunicorn master before any "
        "worker exists (as the Docker image does; opal-server run has no "
        "preload), deletes every clone with a marker before its sync, so the "
        "sync clones it fresh, as on a new pod: if that clone fails or hangs "
        "too (the remote is still unreachable), the source has no clone, and "
        "its scopes no policy, until a clone succeeds, again as on a new pod. "
        "When the marked clones of the current scopes' sources span at least "
        "two of the repositories those scopes have a clone of on disk, and at "
        "least half of them, the hang is most likely the git provider's and "
        "nothing is deleted, so every scope keeps its last fetched policy; "
        "nothing is deleted either when no clone on disk is one the current "
        "scopes use. Do not share BASE_DIR between running servers (see "
        "BASE_DIR); with this on, any marker counts, whoever wrote it. Each "
        "clone deleted "
        "increments opal_server.scopes.hung_clone_recloned. A marked clone "
        "of a repository in SCOPES_READY_REQUIRED_REPOS that had landed is "
        "kept, with a WARNING, and increments "
        "opal_server.scopes.hung_clone_kept: deleting it would keep the "
        "server from Ready until the clone lands again.",
    )
    SCOPES_GIT_MAX_ZOMBIES = confi.int(
        "SCOPES_GIT_MAX_ZOMBIES",
        # 4x the default SCOPES_GIT_MAX_WORKERS. Once this many git ops (live +
        # lingering timed-out) hold a daemon thread, new ops are refused until
        # threads drain, bounding worst-case thread growth during an outage.
        40,
        description="Maximum number of in-flight scope git operations (live plus "
        "lingering timed-out) allowed to hold a daemon thread at once, counted "
        "GLOBALLY across all sources. It is a last-resort ceiling on thread "
        "growth when remotes hang, not a per-source guard — that is handled "
        "separately, by skipping a source that already has an operation in "
        "flight. Once the ceiling is reached, new git ops are refused (logged, "
        "and retried next cycle) for EVERY scope, healthy ones included, until "
        "enough threads drain; with remotes that never return, that state can "
        "persist. Set it well above SCOPES_GIT_MAX_WORKERS and alert on the "
        "refusal log (0 = no cap; a negative value is clamped to 0 and also "
        "means no cap, at the cost of unbounded thread growth during an "
        "outage).",
    )
    SCOPES_GIT_BACKOFF_BASE_SECONDS = confi.float(
        "SCOPES_GIT_BACKOFF_BASE_SECONDS",
        10.0,
        description="First delay before the periodic sync pass re-attempts a "
        "SOURCE whose git clone or fetch just failed (unreachable host, revoked "
        "credentials, deleted repo); every further consecutive failure doubles "
        "it — 10s, 20s, 40s, ... minutes, hours, days — with no upper bound "
        "unless SCOPES_GIT_BACKOFF_MAX_SECONDS is set. A delay shorter than the "
        "gap to the next pass simply does not skip that pass, so the first few "
        "doublings cost one attempt per pass exactly as before and the schedule "
        "bites from roughly the fourth consecutive failure. It exists because "
        "nothing else records a failure: without it every pass re-attempts every "
        "dead repo, and so does every duplicate scope sharing that repo — a "
        "handful of dead repositories can account for thousands of clone attempts "
        "per hour. The periodic pass, the pass after a backbone gap and the boot "
        "preload honour it (in "
        "both phases, and re-checked under the source lock, so duplicates of a "
        "source that fails in a pass cost one attempt, not one per scope), and so "
        "does the sync GET /scopes/:scope_id/policy requests for a scope whose "
        "branch is missing from its clone (SCOPES_POLICY_BRANCH_REFRESH_INTERVAL); "
        "an explicit POST /scopes/:scope_id/refresh, POST /scopes/refresh or "
        "PUT /scopes attempts the source whatever its backoff (a POST "
        "/scopes/refresh made while a sync pass runs is served by the pass that "
        "starts when that one ends), so an operator who has "
        "just repaired credentials recovers at once, and any successful clone or "
        "fetch clears both the delay and the consecutive-failure count. The state "
        "is in-memory and per process — it resets on restart. When a periodic "
        "pass runs (POLICY_REFRESH_INTERVAL > 0) a forked worker inherits "
        "whatever the pre-fork preload recorded, so the leader does not re-hammer "
        "repos that already failed at boot; without one, the boot sync is the "
        "only pass-originated sync, so it drops the inherited entries and "
        "attempts every source once. Watch "
        "opal_server.scopes.sources_in_backoff (gauge of sources currently being "
        "skipped, tagged by pid) and opal_server.scopes.git_op_skipped with "
        "reason:backoff (counter); the WARNING logged when a source enters "
        "backoff, and again when its delay first exceeds a day, names the "
        "repository. 0 or negative disables the backoff entirely — nothing is "
        "recorded and nothing is skipped; nan and inf are treated as disabled "
        "too, because they parse cleanly rather than failing the process at "
        "startup and neither is a duration.",
    )
    SCOPES_GIT_BACKOFF_MAX_SECONDS = confi.float(
        "SCOPES_GIT_BACKOFF_MAX_SECONDS",
        0.0,
        description="Optional cap on the per-source doubling backoff of "
        "SCOPES_GIT_BACKOFF_BASE_SECONDS. 0 (the default), negative, nan or inf "
        "means NO cap: a repository that has been unreachable for a day is "
        "checked again in two, then four, and before long only at the next "
        "restart or explicit refresh — a repository that keeps failing is, in "
        "all likelihood, dead. Set a positive value to bound instead how stale "
        "a repository that comes back on its own (without anyone touching its "
        "scope) can get: the periodic pass then re-attempts it at most that "
        "long after the previous attempt. A value below the base is floored at "
        "the base (one pass at a time), never inert. Lowering the cap at "
        "runtime is not retroactive for delays already armed.",
    )
    SCOPES_GIT_REPACK_PACK_LIMIT = confi.int(
        "SCOPES_GIT_REPACK_PACK_LIMIT",
        50,
        description="Pack-file count at which a scope clone is repacked: once a "
        "successful fetch leaves the clone holding at least this many pack files, "
        "git repack -a -d -k runs on it at the end of the sync pass, after the "
        "pass has sent its notifications, merging them into a single pack and "
        "dropping the duplicate objects. Before it, git pack-refs --all moves the "
        "clone's refs, which libgit2 keeps in a file each, into one packed-refs "
        "file, and the clone's reflogs, which OPAL never reads, are turned off "
        "(core.logAllRefUpdates=false in the clone's config, which new scope "
        "clones are made with) and removed (moved aside within the repack's "
        "timeout, and deleted once the repack has let go of the clone): with a "
        "file of at least one filesystem block per ref, the reflogs of a clone "
        "with tens of thousands of branches can take many times the disk of its "
        "objects. With the libgit2 fetch pruning (SCOPES_GIT_FETCH_WITH_CLI off, "
        "SCOPES_GIT_FETCH_PRUNE on) the refs stay in their files and only the "
        "reflogs go: see SCOPES_GIT_FETCH_PRUNE. A clone whose refs "
        "are not packed (a fresh libgit2 clone, or one made by an earlier "
        "version), or, with the libgit2 fetch pruning, one that still has "
        "reflogs (made by an earlier version), gets these ref steps alone at the "
        "end of the next sync pass after its clone or fetch, without waiting for "
        "the limit. They are "
        "counted as opal_server.scopes.git_pack_refs by outcome, with a "
        "git_pack_refs_seconds distribution, and a git pack-refs (git config, "
        "when the refs stay in their files) that fails "
        "there holds off the clone's repacks for an hour, as a failed repack "
        "does. Before a repack, a ref step that fails is a warning and the "
        "repack still runs; every ref step that fails, runs past its share of "
        "SCOPES_GIT_REPACK_TIMEOUT or leaves the refs in files of their own is "
        "counted as opal_server.scopes.git_ref_step_failures, tagged by step "
        "(config, reflogs or pack_refs). A refresh of a single scope (POST "
        "/scopes/:scope_id/refresh, or a PUT /scopes) repacks its clone right "
        "after its own sync, once its notification is out, so it repacks even "
        "when no periodic pass runs (POLICY_REFRESH_INTERVAL=0). A pass never "
        "waits for a clone another sync or refresh is using: it leaves that clone "
        "to the next pass or refresh. No repack starts while a sync pass runs in "
        "the same process: a repack that a refresh of one scope leaves due while "
        "a pass runs is run at the end of that pass. "
        "Objects no branch reaches any more, those "
        "of branches deleted upstream included, are kept in the merged pack "
        "rather than deleted, so that a repack never removes an object a fetch in "
        "another process is about to point a branch at; the cost is that they "
        "stay until the clone is cloned again. It exists because the scopes git "
        "fetcher (pygit2 on libgit2) writes one new pack file per fetch and never "
        "consolidates them, and a fetch of a repository with many branches can "
        "re-download history the clone already has, so without it the clone's "
        "disk grows without bound until the volume holding the clones fills. It "
        "only affects scopes mode (SCOPES=true): the classic policy-repo path "
        "fetches with the git command line, which cleans up its own packs. The "
        "git binary must be on PATH, and /bin/sh must exist, since each git of a "
        "repack runs under it (the official images ship both); without /bin/sh "
        "every repack fails, and is retried once an hour. The repack "
        "runs inside the opal-server container, one clone at a time per pod, "
        "enforced with an flock on the directory holding the clones: that "
        "directory must be on a local filesystem, or on NFS mounted with "
        "local_lock=flock, since where flock fails every repack fails and is "
        "retried once an hour. Its memory counts against the container's limit: "
        "allow about 0.5 KB per object of the repository. On "
        "Linux git runs with oom_score_adj 1000, so when the container runs out "
        "of memory the kernel picks the repack before an opal-server worker. "
        "Where the whole container is the unit of an OOM kill (Kubernetes on "
        "cgroup v2, unless the kubelet sets singleProcessOOMKill) the container "
        "restarts instead. The repack's attempt marker in the clone then keeps "
        "the restarted server from repacking that clone for an hour (plus the "
        "repack timeout), so the restarts come at most hourly rather than in a "
        "loop, and an INFO line names the clone; they stop only once the memory "
        "limit leaves room for the repack. Size it with that room. It needs "
        "disk too: git "
        "writes the merged pack before it deletes the old ones, so the volume "
        "holding the clones needs free space for about one more copy of the "
        "clone's packs. On a volume that fills up for real, a repack that runs "
        "out of space fails, is logged and is not retried for an hour, and while "
        "it writes, fetches of other clones on that volume can fail as well. On "
        "a Kubernetes emptyDir with a sizeLimit nothing fails: the kubelet "
        "EVICTS the pod (skipping its preStop hook) once the volume passes the "
        "limit, so size the limit with room for one more copy of the largest "
        "clone's packs above its usual peak. A repack that fails, or never "
        "finishes because its process died, is not retried for an hour by any "
        "process of the pod, a new leader included. Each repack put off for a "
        "pass is counted as opal_server.scopes.git_op_skipped with reason "
        "pass_in_flight. Raise the "
        "limit to repack less often; 0 or negative disables repacking, and 1 "
        "counts as 2, since a clone always holds a pack after a fetch.",
    )
    SCOPES_GIT_REPACK_TIMEOUT = confi.float(
        "SCOPES_GIT_REPACK_TIMEOUT",
        120.0,
        description="Hard timeout in seconds for one scope clone repack (see "
        "SCOPES_GIT_REPACK_PACK_LIMIT), its git pack-refs included, and for a "
        "run of its ref steps alone. Before a repack the ref steps get half of "
        "it: past that the one running is stopped, and git repack gets the "
        "rest. Unlike "
        "SCOPES_GIT_FETCH_TIMEOUT it is "
        "HARD: when it expires git gets SIGTERM, then SIGKILL 10 seconds later, "
        "the files and locks it left in the clone are removed, and the clone keeps "
        "the packs it already had. Stopping git can take up to 20 seconds past "
        "the timeout, and OPAL waits for it up to 30 seconds past the timeout, so "
        "once git starts the repack holds the clone's sync lock for at most the "
        "timeout plus 30 seconds (150 seconds with the default), and then for "
        "a walk of the clone's refs/ and logs/ that sizes its log line (as "
        "before git starts), which the timeout does not bound: a walk of the "
        "126,000 files of a clone of a repository with 63,000 branches took "
        "about 0.7 seconds on a local disk with a warm cache. One case "
        "outlives that bound: a git stuck in uninterruptible I/O survives "
        "SIGKILL, and keeps the pod-wide repack lock, so no other repack starts "
        "in the pod until it exits. A git whose opal-server worker exits "
        "mid-repack does not outlive it: git runs under a watchdog that kills "
        "its whole process group once that worker is gone. It must stay bounded "
        "because "
        "the repack holds the clone's sync lock while it runs. Repacks run one at "
        "a time at the end of a sync pass, after its notifications, so within one "
        "pass a repack delays none of them, and a refresh of a single scope runs "
        "its repack right after its own notification. A sync pass runs one at a "
        "time in the leader; a repack that a refresh of one scope leaves due "
        "while a pass runs is run at the end of that pass, since the pass's "
        "syncs would otherwise queue on the clone's lock while holding their "
        "SCOPES_GIT_MAX_WORKERS slots and stall the whole pass, every other "
        "clone's scopes included. A pass that starts while a refresh's repack is "
        "already running still waits for it in the same way, as it does for a "
        "slow fetch. The next pass starts only once the repacks of the one "
        "before are done. The default leaves "
        "several times the time a repack of a clone with tens of thousands of "
        "branches takes, most of it CPU; too low a value is worse than "
        "too high, since a repack that always times out never reclaims any disk. "
        "Watch opal_server.scopes.git_repack with outcome:timeout and the "
        "git_repack_seconds distribution. 0, negative, nan or inf fall back to the default of "
        "120 seconds, and a value over 86400 (a day) is capped at 86400 with a "
        "warning, because a wait of more than about 24 days overflows and fails "
        "every repack; there is no way to set no limit.",
    )
    SCOPES_POLICY_CLONE_WAIT_SECONDS = confi.float(
        "SCOPES_POLICY_CLONE_WAIT_SECONDS",
        20.0,
        description="How long GET /scopes/:scope_id/policy holds a request while "
        "that scope's clone is still being populated, before falling through to "
        "the 503 + Retry-After it answers today. The route re-checks once a "
        "second and returns the bundle the moment the clone is usable. It exists "
        "because the opal-client PDP ignores Retry-After: it makes five attempts "
        "with random-exponential backoff capped at 10s (~20-40s of coverage) and "
        "then stays quiet until the next pub/sub policy message or a reconnect, "
        "so a clone that outlives those attempts strands that PDP with no policy "
        "— and the update-all published when a clone completes names only the "
        "scope that was syncing, so siblings sharing the same clone are not "
        "woken. Holding the request converts that gap into latency the client "
        "already tolerates: five client attempts against a 20s hold cover about "
        "two minutes of clone time, so short and medium re-clones — meaning the "
        "download phase; the rmtree-and-init window before it answers 503 + "
        "Retry-After 5 and is not waited on — produce no client-visible gap. "
        "What this bounds is the WAIT plus at most one more bundle attempt: "
        "time queued behind other bundle builds on the shared executor is "
        "outside the deadline, which is what SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT "
        "bounds instead. The budget matters in both directions — 20s is well "
        "under the 60s ALB idle timeout (a longer hold surfaces as a 504, which "
        "the client cannot tell apart from a dead server) and far under the "
        "client's 300s aiohttp total timeout. Readiness is derived from DISK (the "
        "clone still has no remote-tracking refs, or has not finished its first "
        "clone or fetch: libgit2 clones in place and writes those refs one at a "
        "time, so until then a missing branch may be one it has not written "
        "yet), never from an in-process "
        "marker, so every worker answers alike: the clone runs in the leader "
        "while this route is served by any worker. The wait covers a git "
        "command-line clone in progress too (SCOPES_GIT_FETCH_WITH_CLI): git "
        "clones into a directory beside the clone's path and renames it into "
        "place once complete, so a clone path that does not exist yet, with "
        "that directory beside it and the clone's lock held, counts as a clone "
        "still being populated (a directory left by a clone whose process died "
        "does not count). "
        "The hold is an awaited sleep "
        "loop, so it occupies no thread between polls and leaves the event loop "
        "and the gunicorn worker heartbeat unaffected; it is abandoned early if "
        "the client disconnects. 0 or negative disables the wait (answer 503 "
        "immediately), and with it the branch wait of "
        "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL. nan, inf and -inf are treated as disabled too: unlike a "
        "non-numeric value, which fails this process at startup when the "
        "environment is parsed, they parse cleanly — inf would otherwise mean "
        "the clamped maximum hold on every clone-in-progress request, and nan "
        "is not a budget at all. Values above 55s are clamped to 55s so the "
        "hold can never outlive the load balancer's idle timeout.",
    )
    SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT = confi.int(
        "SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT",
        64,
        description="Maximum number of requests one worker process may hold at "
        "once inside the SCOPES_POLICY_CLONE_WAIT_SECONDS wait, and the "
        "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS one. Requests beyond "
        "the cap get the immediate answer they would have got before the wait "
        "existed (503 + Retry-After 30 for a clone in progress, 409 for a missing "
        "branch; a request without base_hash shed from the "
        "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS wait gets that 409 only when a "
        "fetch of the branch on this server succeeded within that wait before it, "
        "else a 503 with Retry-After 5), so the cap can never make things worse "
        "than not waiting. It exists because polling is cheap but RELEASING is not: "
        "when the clone lands, every held request builds a full bundle on the "
        "loop's DEFAULT executor: about min(32, cpu+4) threads shared by every "
        "off-loop call this process makes, in front of an unbounded queue. "
        "Measured throughput there falls from ~52 bundles/s at 32 concurrent "
        "builds to ~18/s at 1000. Scope git clone/fetch does NOT share that "
        "pool — each op runs on its own single-use daemon-thread executor, "
        "bounded by SCOPES_GIT_MAX_WORKERS through a semaphore — so this key is "
        "the only bound on how many bundle builds can pile up at once. "
        "Size it so the cap divided by the "
        "bundles-per-second that pod can really build fits inside the 60s ALB "
        "idle timeout MINUS the hold: above that, released requests queue past "
        "the timeout and 504 — the very failure the hold exists to prevent — and "
        "a rolling restart drains worse, because uvicorn waits for in-flight "
        "requests while gunicorn SIGKILLs the worker at 30s, dropping every "
        "websocket that worker still holds. The count is per process, not per "
        "pod: a pod running N workers holds up to N times this number. 0 or "
        "negative means no cap.",
    )
    SCOPES_POLICY_BRANCH_REFRESH_INTERVAL = confi.float(
        "SCOPES_POLICY_BRANCH_REFRESH_INTERVAL",
        0.0,
        description="Off by default (0): set it, for example to 60, to enable it. "
        "When GET /scopes/:scope_id/policy finds the scope's clone populated but "
        "without the scope's branch, or finds no clone of the scope's repository "
        "at all, this worker asks every server to sync that "
        "scope and holds the request in the SCOPES_POLICY_CLONE_WAIT_SECONDS wait, "
        "under the same in-flight cap, polling that one branch ref and serving the "
        "bundle as soon as the branch is there. The sync is not forced: a server "
        "fetches only when its own clone "
        "lacks the branch. A branch pushed after a server's last fetch is not a "
        "misconfiguration: right after a PUT /scopes that moves a scope to another "
        "repository, every pod answers this way until its own fetch of that "
        "repository lands, and a pod that missed the PUT's broadcast, or whose "
        "fetch failed, keeps answering it until something else syncs that clone. An "
        "opal-client that starts in that window makes five attempts, then waits for "
        "the next policy message, with no policy loaded. Each worker process "
        "requests that sync at most once per this many seconds per scope and "
        "branch (a scope that a PUT moves to another repository or branch asks "
        "again), and, for a clone it finds missing, once per clone, whichever of "
        "the clone's scopes ask: one sync clones it for all of them. Further "
        "misses on that worker while its request is younger than the "
        "clone wait are held too, without asking again, until the first hold's "
        "deadline; after that, for the rest of the interval, a miss gets the "
        "immediate 409 (503 with no clone) it got before. A clone that has the "
        "scope's branch ref but not the commit it names (an object store gutted "
        "under it) gets the retryable 503 at once, and the worker asks for one "
        "sync of the scope per this many seconds, which deletes the clone and "
        "clones it again. A request shed at the "
        "in-flight cap requests nothing; a request that requests the sync holds "
        "its slot while it does. So a branch that really does not "
        "exist costs, per interval, at most one clone-wait budget of held requests "
        "on each worker that sees a miss (bounded by the in-flight cap), and one "
        "sync request from each of those workers to every server. Every server's "
        "clone lacks a branch that does not exist, so each server fetches once per "
        "sync request, except that requests reaching a server before its next "
        "fetch of that repository starts share that fetch: requests that arrive "
        "together cost one or two fetches, while requests spread over the interval "
        "(one client's retries usually reach different workers seconds apart) cost "
        "one each, under the lock every scope on that clone shares; a server whose "
        "clone has the branch does not fetch. Weigh that before turning this on for a clone with tens of "
        "thousands of branches. These syncs honour the source's failure backoff, so they do not "
        "retry a repository whose fetches keep failing; a server whose fetch has "
        "just failed fetches the branch only for a request that arrives after that "
        "backoff (SCOPES_GIT_BACKOFF_BASE_SECONDS) has passed. A branch pushed "
        "after the fetch a request asked for is not fetched for that scope until "
        "a miss after the interval asks again, or something else syncs it: a "
        "writer that pushes a scope's branch after its PUT /scopes should refresh "
        "the scope (POST /scopes/:scope_id/refresh) after the push. An interval no "
        "longer than SCOPES_POLICY_CLONE_WAIT_SECONDS asks again at the first miss "
        "after each hold. When "
        "the wait runs out with the branch still missing, the answer is that same "
        "409 (a 503 + Retry-After 5 when there is still no clone). 0 or negative "
        "disables it (409 or 503 immediately, as before); nan, inf and "
        "-inf are treated as disabled too. Requires "
        "SCOPES_POLICY_CLONE_WAIT_SECONDS > 0: with that wait disabled, no sync is "
        "requested either. A request without base_hash that waited for this "
        "server's fetch of the branch (SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS) is "
        "not held again for it, nor is one that wait shed at the in-flight cap.",
    )
    SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS = confi.float(
        "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS",
        10.0,
        description="With SCOPES_GIT_FETCH_WITH_CLI on: how long GET "
        "/scopes/:scope_id/policy without base_hash (a client that holds no policy "
        "yet) waits for this server's fetch of the scope's branch before it builds "
        "the bundle. A git command-line fetch asks only for the branches its syncs "
        "need, so a server that missed a refresh of the scope is not caught up by "
        "the fetches of other scopes, and would serve such a client its old head. "
        "The request asks every server to fetch the scope's branch, honouring the "
        "source's failure backoff, and only a fetch that started after it asked "
        "counts: a clone or a fetch that started before, however recent, may "
        "predate a branch or a commit pushed since. One worker asks once per "
        "scope until the fetch it asked for has ended (or this wait has passed), "
        "and the requests meanwhile wait for that fetch; the first request after "
        "it asks again. A server answers such a request from a fetch of the "
        "branch that started after the request reached it, without fetching "
        "again: during a storm of clients starting each server fetches the "
        "branch one fetch after another. A fetch of the branch on this server "
        "that failed within this many seconds before the request answers it at "
        "once, without asking (the source is in its failure backoff, which the "
        "fetch asked for would honour). The bundle is built as soon as such a "
        "fetch of the branch on this server has succeeded or failed (read from "
        "the clone's fetch marks, see SCOPES_GIT_FETCH_WITH_CLI), or when the "
        "wait is over, from what the clone holds then. A branch the clone does not "
        "have then is a 503 with Retry-After 5 after a fetch that failed or did not "
        "end in time, and the 409 after one that succeeded (the remote has no such "
        "branch), without the hold of SCOPES_POLICY_BRANCH_REFRESH_INTERVAL. Only "
        "for a clone that has landed (SCOPES_POLICY_CLONE_WAIT_SECONDS covers one "
        "that has not) and a branch that can be a git ref. A waiting request holds "
        "a slot of SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT; with none free it is "
        "served without waiting, nor held by the branch wait, and a branch the "
        "clone does not have is the 409 only when a fetch of it on this server "
        "succeeded within this many seconds before the request, else a 503 with "
        "Retry-After 5. Any client allowed to read the scope's policy can "
        "make every server fetch its branch this way, one fetch after another "
        "while such requests keep coming (before 0.10 only POST "
        "/scopes/:scope_id/refresh, a datasource token's, forced a fetch). A "
        "request usually waits about one fetch (two when one is already running) "
        "and a broadcast round trip. 0, a negative value, nan and inf: no wait; "
        "above 55 it is clamped to 55, as the clone wait is, and the clone wait a "
        "request holds after this one gets what is left of 55 seconds. Requests "
        "with base_hash never wait, nor any with SCOPES_GIT_FETCH_WITH_CLI off.",
    )
    SCOPES_MISSING_SCOPE = confi.str(
        "SCOPES_MISSING_SCOPE",
        "default",
        description="What GET /scopes/:scope_id/policy and GET "
        "/scopes/:scope_id/data answer for a scope that is not stored. default: "
        "the policy of the scope named default (a 404 when that one is not stored "
        "either), and an empty data configuration, or a redirect to the "
        "external_source_url of OPAL_DATA_CONFIG_SOURCES when it has one. "
        "not_found: a 404 for both, so a client whose scope is gone keeps the "
        "policy and data it has and never loads the default scope's policy. With "
        "either, each such request logs a WARNING and counts "
        "opal_server.scopes.missing_scope, tagged with the route (policy or data; "
        "the WARNING names the scope), and is posted to "
        "SCOPES_MISSING_SCOPE_WEBHOOK_URL when that is set. The server does not "
        "start in scopes mode with any other value.",
    )
    SCOPES_MISSING_SCOPE_WEBHOOK_URL = confi.str(
        "SCOPES_MISSING_SCOPE_WEBHOOK_URL",
        None,
        description="An http:// or https:// URL that a worker POSTs to when a "
        "policy or data request finds a scope that is not stored (see "
        "SCOPES_MISSING_SCOPE), so that whatever writes the scopes can put it "
        "back. The body is a JSON object with scope_id, route (policy or data) and "
        "seen_at (when the request came, ISO 8601, UTC), sent with "
        "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN as a Bearer token when that is set. "
        "Each worker posts a scope at most once per 5 minutes, in the background "
        "(the request does not wait for it), with a 5-second timeout and no "
        "retry, and at most 100 at a time: a scope seen while 100 are under way "
        "is posted at a later request for it. Each POST is counted in "
        "opal_server.scopes.missing_scope_webhook by outcome. Of the URL, only its "
        "scheme, host and port are logged. The server does not start in scopes mode when this is not an "
        "http:// or https:// URL with a host, or carries a password while "
        "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN is set. Unset, nothing is posted.",
        sensitive=True,
    )
    SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN = confi.str(
        "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN",
        None,
        description="The Bearer token of the SCOPES_MISSING_SCOPE_WEBHOOK_URL "
        "POSTs, sent as their Authorization header and never logged. Unset, the "
        "POSTs carry no Authorization header. The server does not start in scopes "
        "mode when this is set without SCOPES_MISSING_SCOPE_WEBHOOK_URL.",
        sensitive=True,
    )
    LEADER_LOCK_FILE_PATH = confi.str(
        "LEADER_LOCK_FILE_PATH",
        "/tmp/opal_server_leader.lock",
        description="The path to the leader lock file",
    )
    POLICY_BUNDLE_SERVER_TYPE = confi.enum(
        "POLICY_BUNDLE_SERVER_TYPE",
        PolicyBundleServerType,
        PolicyBundleServerType.HTTP,
        description="The type of bundle server e.g. basic HTTP , AWS S3. (affects how we authenticate with it)",
    )
    POLICY_BUNDLE_SERVER_TOKEN = confi.str(
        "POLICY_BUNDLE_SERVER_TOKEN",
        None,
        description="Secret token to be sent to API bundle server",
        sensitive=True,
    )
    POLICY_BUNDLE_SERVER_TOKEN_ID = confi.str(
        "POLICY_BUNDLE_SERVER_TOKEN_ID",
        None,
        description="The id of the secret token to be sent to API bundle server",
        sensitive=True,
    )
    POLICY_BUNDLE_SERVER_AWS_REGION = confi.str(
        "POLICY_BUNDLE_SERVER_AWS_REGION",
        "us-east-1",
        description="The AWS region of the S3 bucket",
    )
    POLICY_BUNDLE_TMP_PATH = confi.str(
        "POLICY_BUNDLE_TMP_PATH",
        "/tmp/bundle.tar.gz",
        description="Path for temp policy file, need to be writeable",
    )
    POLICY_BUNDLE_GIT_ADD_PATTERN = confi.str(
        "POLICY_BUNDLE_GIT_ADD_PATTERN",
        "*",
        description="Git pathspec (as git add takes it) of the API source bundle's files "
        "to commit and serve, read with no host git config. * takes every file but those "
        "a .gitignore in the bundle ignores (a file once committed stays tracked)",
    )

    REPO_WATCHER_ENABLED = confi.bool(
        "REPO_WATCHER_ENABLED",
        True,
        description="Enable the repository watcher. In scopes mode (SCOPES=true) this "
        "same flag enables the scopes sync task on the leader worker: the periodic "
        "sync_scopes pass, the post-leadership sync of all scopes and the fleet "
        "purger. It does NOT gate the pre-fork preload, which still clones/fetches "
        "every registered scope at boot. With the flag off, scopes are registered, "
        "preloaded at boot and served, but never re-synced or purged afterwards.",
    )

    # publisher
    PUBLISHER_ENABLED = confi.bool(
        "PUBLISHER_ENABLED", True, description="Enable the publisher"
    )

    # broadcaster keepalive
    BROADCAST_KEEPALIVE_INTERVAL = confi.int(
        "BROADCAST_KEEPALIVE_INTERVAL",
        3600,
        description="the time to wait between sending two consecutive broadcaster keepalive messages",
    )
    BROADCAST_KEEPALIVE_TOPIC = confi.str(
        "BROADCAST_KEEPALIVE_TOPIC",
        "__broadcast_session_keepalive__",
        description="the topic on which we should send broadcaster keepalive messages",
    )

    # statistics
    MAX_CHANNELS_PER_CLIENT = confi.int(
        "MAX_CHANNELS_PER_CLIENT",
        15,
        description="max number of records per client, after this number it will not be added to statistics, relevant only if STATISTICS_ENABLED",
    )
    STATISTICS_WAKEUP_CHANNEL = confi.str(
        "STATISTICS_WAKEUP_CHANNEL",
        "__opal_stats_wakeup",
        description="The topic a waking-up OPAL server uses to notify others he needs their statistics data",
    )
    STATISTICS_STATE_SYNC_CHANNEL = confi.str(
        "STATISTICS_STATE_SYNC_CHANNEL",
        "__opal_stats_state_sync",
        description="The topic other servers with statistics provide their state to a waking-up server",
    )
    STATISTICS_SERVER_KEEPALIVE_CHANNEL = confi.str(
        "STATISTICS_SERVER_KEEPALIVE_CHANNEL",
        "__opal_stats_server_keepalive",
        description="The topic workers use to signal they exist and are alive",
    )
    STATISTICS_SERVER_KEEPALIVE_TIMEOUT = confi.str(
        "STATISTICS_SERVER_KEEPALIVE_TIMEOUT",
        20,
        description="Timeout for forgetting a server from which a keep-alive haven't been seen (keep-alive frequency would be half of this value)",
    )
    SCOPES_PURGE_CHANNEL = confi.str(
        "SCOPES_PURGE_CHANNEL",
        "__opal_scope_purge__",
        description="Pub/sub channel (worker-to-worker, over the broadcaster) used to "
        "purge GitPolicyFetcher caches fleet-wide when a scope is deleted or "
        "repointed to a new source. Every worker subscribes and drops its own "
        "cache entries; the leader is the only actor that may authorize that, "
        "because only it can check whether a surviving scope still shares the "
        "source. It does not remove the clone dir.",
    )

    # Data updates
    ALL_DATA_TOPIC = confi.str(
        "ALL_DATA_TOPIC",
        DEFAULT_DATA_TOPIC,
        description="Top level topic for data",
    )
    ALL_DATA_ROUTE = confi.str(
        "ALL_DATA_ROUTE", "/policy-data", description="The route for all policy data"
    )
    ALL_DATA_URL = confi.str(
        "ALL_DATA_URL",
        confi.delay("http://localhost:7002{ALL_DATA_ROUTE}"),
        description="URL for all data config [If you choose to have it all at one place]",
    )
    DATA_CONFIG_ROUTE = confi.str(
        "DATA_CONFIG_ROUTE",
        "/data/config",
        description="URL to fetch the full basic configuration of data. A POST to it "
        "triggers a data update event",
    )
    DATA_CALLBACK_DEFAULT_ROUTE = confi.str(
        "DATA_CALLBACK_DEFAULT_ROUTE",
        "/data/callback_report",
        description="Exists as a sane default in case the user did not set OPAL_DEFAULT_UPDATE_CALLBACKS",
    )

    DATA_CONFIG_SOURCES = confi.model(
        "DATA_CONFIG_SOURCES",
        ServerDataSourceConfig,
        confi.delay(
            lambda ALL_DATA_URL="", ALL_DATA_TOPIC="": {
                "config": {
                    "entries": [{"url": ALL_DATA_URL, "topics": [ALL_DATA_TOPIC]}]
                }
            }
        ),
        description="Configuration of data sources by topics",
    )

    # Git service webhook (Default is Github)
    POLICY_REPO_WEBHOOK_SECRET = confi.str(
        "POLICY_REPO_WEBHOOK_SECRET",
        None,
        description="The secret for the policy repository webhook",
        sensitive=True,
    )
    # The topic the event of the webhook will publish
    POLICY_REPO_WEBHOOK_TOPIC = "webhook"
    # Should we check the incoming webhook mentions the branch by name- and not just in the URL
    POLICY_REPO_WEBHOOK_ENFORCE_BRANCH: bool = confi.bool(
        "POLICY_REPO_WEBHOOK_ENFORCE_BRANCH",
        False,
        description="Enforce branch name in incoming webhook",
    )
    # Parameters controlling how the incoming webhook should be read and processed
    POLICY_REPO_WEBHOOK_PARAMS: GitWebhookRequestParams = confi.model(
        "POLICY_REPO_WEBHOOK_PARAMS",
        GitWebhookRequestParams,
        {
            "secret_header_name": "x-hub-signature-256",
            "secret_type": "signature",
            "secret_parsing_regex": "sha256=(.*)",
            "event_header_name": "X-GitHub-Event",
            "event_request_key": None,
            "push_event_value": "push",
        },
        description="Parameters for processing the incoming webhook",
    )

    POLICY_REPO_POLLING_INTERVAL = confi.int(
        "POLICY_REPO_POLLING_INTERVAL",
        0,
        description="The polling interval for the policy repository",
    )

    ALLOWED_ORIGINS = confi.list(
        "ALLOWED_ORIGINS", ["*"], description="List of allowed origins for CORS"
    )
    FILTER_FILE_EXTENSIONS = confi.list(
        "FILTER_FILE_EXTENSIONS",
        [".rego", ".json"],
        description="List of file extensions to filter. Example: ['.rego', '.json']",
    )
    BUNDLE_IGNORE = confi.list(
        "BUNDLE_IGNORE", [], description="List of patterns to ignore in the bundle"
    )

    NO_RPC_LOGS = confi.bool(
        "NO_RPC_LOGS",
        True,
        description=(
            "Suppress DEBUG logs of the websocket RPC/pub-sub libraries, which "
            "include message payloads (INFO and above are kept)"
        ),
    )

    # client-api server
    SERVER_WORKER_COUNT = confi.int(
        "SERVER_WORKER_COUNT",
        None,
        description="(if run via CLI) Worker count for the server [Default calculated to CPU-cores]",
    )

    SERVER_HOST = confi.str(
        "SERVER_HOST",
        "127.0.0.1",
        description="(if run via CLI)  Address for the server to bind",
    )

    SERVER_PORT = confi.str(
        "SERVER_PORT",
        None,
        # Users have experienced errors when kubernetes sets the env-var OPAL_SERVER_PORT="tcp://..." (which fails to parse as a port integer).
        description="Deprecated, use SERVER_BIND_PORT instead",
    )

    SERVER_BIND_PORT = confi.int(
        "SERVER_BIND_PORT",
        7002,
        description="(if run via CLI)  Port for the server to bind",
    )

    # optional APM tracing with datadog
    ENABLE_DATADOG_APM = confi.bool(
        "ENABLE_DATADOG_APM",
        False,
        description="Set if OPAL server should enable tracing with datadog APM",
    )

    DEBUG_INTERNAL_STATS = confi.bool(
        "DEBUG_INTERNAL_STATS",
        False,
        description=(
            "Expose GET /internal/git-fetcher-cache-stats with in-memory cache "
            "sizes and process RSS. For diagnostics/tests only; keep off in production."
        ),
    )

    SCOPES = confi.bool("SCOPES", default=False, description="Enable scopes")

    SCOPES_REPO_CLONES_SHARDS = confi.int(
        "SCOPES_REPO_CLONES_SHARDS",
        1,
        description="With SCOPES_GIT_FETCH_WITH_CLI off: the number of local "
        "clones of the same repository (reused across scopes) that libgit2 "
        "spreads its scopes over, by branch. With SCOPES_GIT_FETCH_WITH_CLI on "
        "(the default) each repository has one clone and this is ignored, with "
        "a WARNING at start when it is not 1. That clone is libgit2's first "
        "one (its directory name ends in -0), so a server switched to the git "
        "command line fetches it without cloning again, and the clones of the "
        "other shards stay unused in BASE_DIR's git_sources directory until "
        "they are removed, by hand or by SCOPES_ORPHAN_SWEEP_INTERVAL's sweep. "
        "The server does not start in scopes mode when this is below 1.",
    )
    SCOPES_READY_REQUIRED_REPOS = confi.list(
        "SCOPES_READY_REQUIRED_REPOS",
        [],
        description="In scopes mode, the repositories whose clones must have "
        "landed before /healthcheck answers 200: a comma-separated list of "
        "repository URLs, "
        "each written exactly as the scopes' policy sources write it. Until "
        "every clone of each has finished its first clone, /healthcheck "
        "answers 503 with the missing clones' directory names in BASE_DIR's "
        "git_sources directory (never a URL), and "
        "opal_server.scopes.ready_clones_missing reports how many; "
        "/healthz/started waits for the same clones. A directory "
        "a clone is still writing does not count. Once a worker has seen a "
        "clone landed it does not look again: a later failed fetch, a remote "
        "that is down, or the clone deleted and cloned again does not fail "
        "readiness. A worker forked from the gunicorn master starts with what "
        "the pre-fork scope preload saw. Each repository has one clone: with "
        "SCOPES_GIT_FETCH_WITH_CLI off (libgit2) and SCOPES_REPO_CLONES_SHARDS "
        "above 1 the server does not start in scopes mode with this set, since "
        "a shard no scope's branch maps to would never clone and the server "
        "would never get Ready. A URL no stored scope uses never clones "
        "either, so /healthcheck stays 503 until a stored scope uses that URL: "
        "the sync passes (the pre-fork preload's and the leader's) log a "
        "WARNING for it, once per process, with the URL masked and the number "
        "of stored scopes. There is no grace period: a new server is not Ready "
        "until its first clones land, so size a deployment's rollout deadline "
        "for them. Empty (the default), readiness does not look at the clones. "
        "The list is read like a shell word list (a # starts a comment, and "
        "quotes and backslashes are removed), so the server does not start in "
        "scopes mode when an entry holds a #, a quote or a backslash "
        "(percent-encode them in a URL), is blank, or starts with [ or ends "
        "with ] (a JSON list). A URL can carry a credential, so the value is "
        "never logged.",
        sensitive=True,
    )

    REDIS_URL = confi.str(
        "REDIS_URL",
        default="redis://localhost",
        description="The URL for the Redis server",
    )

    BASE_DIR = confi.str(
        "BASE_DIR",
        default=pathlib.Path.home() / ".local/state/opal",
        description="The base directory for OPAL. In scopes mode the scope "
        "clones are in its git_sources directory. Two running servers must not "
        "share it, with SCOPES_GIT_FETCH_WITH_CLI on or off: at each start the "
        "pre-fork scope preload removes the lock files and partial packs it "
        "finds in every clone there, and the clones half made beside them, "
        "whichever server's git op they belong to. In scopes mode the leader "
        "worker writes its heartbeat there too (scopes-leader.heartbeat), which "
        "/healthz/live and /healthz/started read.",
    )

    POLICY_REFRESH_INTERVAL = confi.int(
        "POLICY_REFRESH_INTERVAL",
        default=0,
        description="Policy polling refresh interval",
    )

    SCOPES_STORE_READ_TIMEOUT = confi.float(
        "SCOPES_STORE_READ_TIMEOUT",
        10.0,
        description="Timeout for a scope-store read taken while holding a source's "
        "lock — the sibling check a delete/repoint purge runs before authorizing "
        "the fleet-wide cache purge. The Redis client is built without a socket timeout, so without "
        "this an unreachable store would pin that lock for the life of the process "
        "and block every later sync, purge and delete for the source. On expiry "
        "the sibling check fails open, and what that decides is the fleet-wide "
        "MEMORY purge only — the leader no longer touches the clone tree: a "
        "DELETE confirms it defensively (its record is already gone, so "
        "withholding would strand the fleet's cache entries, while over-purging "
        "self-heals on the surviving sibling's next sync), a REPOINT withholds "
        "it (the old source's record is still live, just moved). The clone dir "
        "is unaffected either way: on a store fault the delete floor KEEPS this "
        "worker's clone rather than risk deleting one a live sibling shares, "
        "leaving an orphan clone dir for SCOPES_ORPHAN_SWEEP_INTERVAL's sweep "
        "(0 or negative means no timeout).",
    )
    SCOPES_ORPHAN_SWEEP_INTERVAL = confi.float(
        "SCOPES_ORPHAN_SWEEP_INTERVAL",
        0.0,
        description="In scopes mode, with REPO_WATCHER_ENABLED on, how often "
        "(seconds) the leader worker looks in BASE_DIR's git_sources directory "
        "for scope clones no stored scope uses any more, and removes them: a "
        "deleted or repointed scope's clone, one whose delete never reached "
        "this server, the shard clones the git command line or a change of "
        "SCOPES_REPO_CLONES_SHARDS leaves unused, a clone left by a crash. 0 "
        "(the default), negative or not finite: off. A clone goes only once two "
        "looks at least this far apart found no stored scope using it, with "
        "none in between finding one; a look decides nothing when the scope "
        "store fails, or when a scope its keys list (as GET /scopes/ids lists "
        "them) reads back although the listing of the records missed it. "
        "Nothing goes while the store lists no scope at all, or while more than "
        "SCOPES_ORPHAN_SWEEP_MAX_SHARE of the clones are unused, and after such "
        "a refusal a clone goes only once two looks in a row found the store no "
        "bigger, so a store being refilled keeps the clones of the scopes still "
        "to come. Only a real directory named like a clone counts, never a "
        "symlink, and the clones of SCOPES_READY_REQUIRED_REPOS are kept. "
        "Right before a clone goes, holding its lock_source, the sweep reads "
        "the store's records again, and reads back each scope its branches "
        "name, bounded by SCOPES_STORE_READ_TIMEOUT: a scope stored since the "
        "look that uses the clone keeps it. It goes under its clone's lock and "
        "the repack lock, taken without waiting: a clone a git op, a repack or "
        "a delete holds is kept for the next look. With it go its hung-op "
        "markers, the directories a clone of it was being made in, the SSH "
        "host keys recorded for it, so the next clone of that repository "
        "trusts the key its host shows on first use again, and its lock file. "
        "At most 16 go per look; one that cannot be removed is tried again one "
        "interval later, then two, four and so on. Each look also removes, in "
        "the clones it keeps, the fetch marks of branches no stored scope of "
        "the clone tracks. A scope whose record Redis evicted, or a restore "
        "lost, counts as deleted: its clone goes, and is cloned again once the "
        "record is back. What a look saw lives in the leader's memory, so a "
        "restart or a new leader starts over, which delays a removal and never "
        "hastens one.",
    )
    SCOPES_ORPHAN_SWEEP_MAX_SHARE = confi.float(
        "SCOPES_ORPHAN_SWEEP_MAX_SHARE",
        0.5,
        description="The most of the scope clones in BASE_DIR's git_sources "
        "directory (real directories named like a clone, the clones of "
        "SCOPES_READY_REQUIRED_REPOS not counted) that the orphan sweep "
        "(SCOPES_ORPHAN_SWEEP_INTERVAL) may find unused and still remove any: "
        "above it, a look removes nothing, forgets what it saw, and counts "
        "opal_server.scopes.orphan_sweep with outcome refused. A scope store "
        "that lost its scopes, or a server pointed at another store, looks "
        "like one whose scopes were all deleted, so after a wipe the clones "
        "stay until the store is right again or this is raised; a store that "
        "lists no scope at all is refused whatever the share, unless this is "
        "1.0. Equal to it is allowed, and 1.0 turns the guard off. Read as 0 "
        "to 1; not a number reads as 0, which refuses while any clone is "
        "unused.",
    )

    def on_load(self):
        if self.SERVER_PORT is not None and self.SERVER_PORT.isdigit():
            # Backward compatibility - if SERVER_PORT is set with a valid value, use it as SERVER_BIND_PORT
            self.SERVER_BIND_PORT = int(self.SERVER_PORT)


opal_server_config = OpalServerConfig(prefix="OPAL_")
