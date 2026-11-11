# OPAL Scopes

OPAL Scopes allows OPAL to serve different policies and data sources,
serving them to multiple clients. Every scope contains its own policy and
data sources. All clients using the same Scope ID will get the same policy
and data.

Scopes are an easy way to use OPAL with multiple Git repositories
(or other sources of policy), and are a core feature to enable using
OPAL itself as a multi-tenant service.

Scopes are dynamic, and can be created on the fly through the scopes
API (`/scopes`)

## Setting up scopes

> #### Prerequisites
>
> Scopes are supported in OPAL 0.2.0 and above. Use the
> [provided docker compose example](https://github.com/permitio/opal/blob/master/docker/docker-compose-scopes-example.yml)
> to quickly get started.
>
> The server must be started with the environment variable
> `OPAL_SCOPES=1`.
>
> The scope clones are kept under
> [`OPAL_BASE_DIR`](/getting-started/configuration#opal_base_dir), which two
> running servers must not share: at each start, the pre-fork scope preload
> removes the lock files and partial packs in every clone there, whichever
> server's git op left them.

### Use a REST API call to create or change a scope

In this scenario, we create two different scopes (_internal_ and _external_),
that, for example, can be used for an internal and external facing app.
The _internal_ scope uses policies located in the _internal_ directory,
and _external_ uses policies defined in the external directory. We can set
different directories, different branches, different repositories, and any
other setting.

The authorization used in this example are GitHub Personal Access Tokens that
can be [generated here](https://github.com/settings/tokens).

```bash
curl --request PUT 'http://opal_server/scopes'
--header 'Content-Type: application/json'
--header 'Authorization: $OPAL_TOKEN'
--data-raw '{
  "scope_id": "internal",
  "policy": {
    "source_type": "git",
    "url": "https://github.com/company/policy",
    "auth": {
      "auth_type": "github_token",
      "token": "github_token"
    },
    "directories": [
      "internal"
    ],
    "extensions": [
      ".rego",
      ".json"
    ],
    "manifest": ".manifest",
    "poll_updates": true,
    "branch": "main"
  },
  "data": {
    "entries": []
  }
}'
```

```bash
curl --request PUT 'http://opal_server/scopes'
--header 'Content-Type: application/json'
--header 'Authorization: $OPAL_TOKEN'
--data-raw '{
  "scope_id": "external",
  "policy": {
    "source_type": "git",
    "url": "https://github.com/company/policy",
    "auth": {
      "auth_type": "github_token",
      "token": "github_token"
    },
    "directories": [
      "external"
    ],
    "extensions": [
      ".rego",
      ".json"
    ],
    "manifest": ".manifest",
    "poll_updates": true,
    "branch": "main"
  },
  "data": {
    "entries": []
  }
}'
```

`PUT /scopes` refuses, with 422, a branch name git can't fetch (such as `x~1`
or an empty name), since such a scope can't follow a branch. A scope stored
with such a name before this release keeps being served as it was until it is
changed. A scope whose branch is not on the remote gets no policy
(`GET /scopes/<scope_id>/policy` answers 409), and the server logs
`Did not find target branch on remote: <branch> (<url>)` at ERROR; a sync pass
logs it once for each branch of each clone.

### Launch OPAL Client with a scope

```bash
docker run -it \
  --env OPAL_CLIENT_TOKEN \
  --env OPAL_SERVER_URL \
  --env OPAL_DATA_TOPICS \
  --env OPAL_SCOPE_ID=internal \
  -p 7766:7000 \
  -p 8181:8181 \
  permitio/opal-client
```

## How the server fetches scope repositories

The server clones and fetches each scope's repository with the git command
line, git 2.32 or later, run under `/bin/sh`, with `ssh` for SSH sources. The
official images have all three. Each repository has one clone, which every
scope on it shares. A clone gets
[`OPAL_SCOPES_GIT_CLONE_TIMEOUT`](/getting-started/configuration#opal_scopes_git_clone_timeout)
(by default 5 times `OPAL_SCOPES_GIT_FETCH_TIMEOUT`), and a fetch
[`OPAL_SCOPES_GIT_FETCH_TIMEOUT`](/getting-started/configuration#opal_scopes_git_fetch_timeout);
git is stopped at either. The server checks for git and `/bin/sh` at start
only with `OPAL_SCOPES` on; a policy repository tracked outside scopes mode
(`OPAL_POLICY_SOURCE_TYPE=GIT`, the default) runs git too.

A fetch asks the remote only for the branches its syncs need, over git's
protocol v2, so the server lists and sends only those branches. A refresh of
a scope, a `PUT /scopes`, or a policy request for a branch the clone does not
have yet fetches that scope's branch; the syncs that wait while a clone is
being fetched share its next fetch. A sync pass (at start, after the
broadcast backbone reconnects, `POST /scopes/refresh`, the periodic one)
fetches every branch the stored scopes track, in one fetch per clone, or
every branch of the repository when they are more than
[`OPAL_SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES`](/getting-started/configuration#opal_scopes_git_cli_narrow_fetch_max_branches)
(1,000 by default).

libgit2 is the second backend:
[`OPAL_SCOPES_GIT_FETCH_WITH_CLI`](/getting-started/configuration#opal_scopes_git_fetch_with_cli)`=false`
selects it, and with it `OPAL_SCOPES_REPO_CLONES_SHARDS` clones per
repository. The reference entry of that setting lists what the two backends
do differently.

### SSH host keys

An SSH source's host key is trusted on first use: the first fetch or clone
records it, and a later op refuses a different key. The fetch fails with
reason `host_key` in `opal_server.scopes.git_op_failures`, the source is
backed off, and the server logs an ERROR that names the record:

- the git command line keeps one record per clone, beside it in
  `OPAL_BASE_DIR`'s `git_sources` directory (`.<clone>.known_hosts`), with
  the key of the type ssh negotiated;
- libgit2 keeps one for all clones, `git_sources/.libgit2-home/.ssh/known_hosts`,
  with each key `ssh-keyscan` reads from the host the first time (it needs
  `ssh-keyscan` on `PATH`), under the host's name as the source's URL writes
  it.

A clone made again keeps its record. When a host does change its key, delete
its record (with libgit2, the host's lines in it) on each server, then refresh
the scope (`POST /scopes/<scope_id>/refresh`, or a `PUT` of the scope): the
source stays backed off until then, and that fetch records the new key. On
Kubernetes with the clones on an `emptyDir`, a new pod starts with no record,
so a rollout records every host again.

[`OPAL_SCOPES_GIT_SSH_KNOWN_HOSTS`](/getting-started/configuration#opal_scopes_git_ssh_known_hosts)
replaces trust on first use, with either backend: only the hosts and keys in
that file are accepted, and nothing is recorded.

### Upgrading from 0.9

0.9 fetched with libgit2 unless `OPAL_SCOPES_GIT_FETCH_WITH_CLI` was on. From
0.10 the git command line is the default:

- A server in scopes mode does not start without git 2.32 or later and
  `/bin/sh`; the error names `OPAL_SCOPES_GIT_FETCH_WITH_CLI=false`, which
  keeps libgit2. A server installed from the Python packages needs git on its
  `PATH`.
- `OPAL_SCOPES_REPO_CLONES_SHARDS` is ignored with the git command line, with a
  WARNING at start when it is not 1: remove it. A value below 1 stops the
  server, with either backend.
- A server that restarts on the same `OPAL_BASE_DIR` fetches libgit2's first
  clone of each repository (the directory whose name ends in `-0`) without
  cloning again. The clones of the other shards are no longer used; remove
  them by hand. A Kubernetes pod on an `emptyDir` starts with an empty volume
  and makes one clone per repository.
- The clone timeout is hard: a clone still running at
  `OPAL_SCOPES_GIT_CLONE_TIMEOUT` is stopped and never lands, where libgit2
  let a slow clone finish in the background. Measure a clone of your largest
  repository and set the timeout above it, with room to spare. A value below
  `OPAL_SCOPES_GIT_FETCH_TIMEOUT` stops the server. The pre-fork preload waits
  for each clone, so a start can take up to this timeout, plus
  `OPAL_SCOPES_GIT_CLI_KILL_GRACE`, while a remote stalls: size startup
  probes for it (by default 600 seconds, where 0.9's libgit2 clone gave up
  after 120).
- git reads neither the system's nor the user's git config (a `url.insteadOf`
  there no longer applies), and OpenSSH refuses a git server that offers only
  an `ssh-rsa` host key, which libgit2 accepted.
- A fetch no longer brings every branch: a clone that missed a refresh of a
  scope catches up at that scope's next refresh or the next sync pass, not at
  a fetch for another scope. `FETCH_HEAD`'s age is still that of the clone's
  last fetch that succeeded, of whatever branches.
  `OPAL_SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES=0` makes every fetch fetch
  every branch, as 0.9 did.
- SSH host keys are trusted on first use with both backends (see above),
  where 0.9 accepted any key unless `OPAL_SCOPES_GIT_SSH_KNOWN_HOSTS` was set
  with the git command line. A host behind a load balancer whose nodes have
  different keys fails on the nodes whose key was not recorded.
- A server in scopes mode does not start when `OPAL_BASE_DIR`'s `git_sources`
  path holds whitespace, `%`, `$`, a quote or a backslash (the git command
  line, without `OPAL_SCOPES_GIT_SSH_KNOWN_HOSTS`), or `:` or `$` (libgit2).
- An `OPAL_SCOPES_GIT_SSH_KNOWN_HOSTS` that cannot be read stops a server on
  libgit2 too, where 0.9 logged an ERROR and ignored it.
- libgit2's SSH sources need `ssh-keyscan` on `PATH`, unless
  `OPAL_SCOPES_GIT_SSH_KNOWN_HOSTS` is set.

### OpenShift and other arbitrary user ids

OpenShift runs a container under an arbitrary user id in group 0, whatever
user the image names. To run the server there:

- Make what the server writes writable by group 0, in an image built on the
  official one: `chgrp -R 0 /opal && chmod -R g=u /opal`. Or put
  `OPAL_BASE_DIR`, where the scope clones are, on a volume the user id can
  write.
- Set `HOME=/opal`. Without a user database entry for the user id, `HOME`
  may not be the image user's home, and defaults that are under it
  (`OPAL_BASE_DIR`, the policy repository's SSH key file) then point
  elsewhere.
- `ssh` does not run under a user id with no entry in the user database
  (`/etc/passwd`), so every scope source fetched over SSH fails there; the
  server logs it at ERROR at start, and HTTPS sources are not affected. Run
  the server as the image's own user, give the user id an entry with
  `nss_wrapper` (its `LD_PRELOAD` and `NSS_WRAPPER_*` variables reach git and
  ssh), or fetch scopes with libgit2
  (`OPAL_SCOPES_GIT_FETCH_WITH_CLI=false`), which needs no entry. A policy
  repository tracked over SSH outside scopes mode runs git and ssh too, and
  needs an entry with either backend.
