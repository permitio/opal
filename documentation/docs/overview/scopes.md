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
with such a name by an earlier release counts as one whose branch is not on the
remote until a `PUT` gives it a real branch. A scope's branch is looked up by its exact
name, `refs/remotes/origin/<branch>`, so a tag of the same name is never served
in its place. A scope whose branch is not on the remote gets no policy
(`GET /scopes/<scope_id>/policy` answers 409), and the server logs
`Did not find target branch on remote: <branch> (<url>)` at ERROR; a sync pass
logs it once for each branch of each clone.

### A scope's data sources

A client of a scope fetches the scope's `data.entries` from
`GET /scopes/<scope_id>/data` when it connects. Each entry is served with its
topics as `<scope_id>:data:<topic>`, the topics the client subscribes to (its
`OPAL_DATA_TOPICS`, each prefixed with its scope id); a topic already written
that way is served as it is, and the stored scope keeps its topics as they
were written.

A `PUT /scopes` that creates a scope with data entries, or changes a scope's
`data`, also publishes those entries, with the same topics, as a data update
to the scope's connected clients, as soon as it has stored the scope. So a
client that connected before its scope existed gets the scope's data without
reconnecting. The client fetches a pushed entry once: an entry's
`periodic_update_interval` polling starts at the client's next connect. A
`PUT` that leaves `data` as it was publishes no data update. Each entry goes
out whole, as `GET /scopes/<scope_id>/data` serves it.

A `PUT` that fails before the data update was published (for example, the
scope store answered an error) logs a WARNING. When the store kept the record
anyway, a retry of the `PUT` finds the data stored and publishes nothing: the
scope's connected clients get the new entries when they next connect.

`POST /scopes/<scope_id>/data/update` gives its entries the same topics.

For a scope that is not stored, `GET /scopes/<scope_id>/data` answers an
empty configuration, or redirects to the `external_source_url` of
[`OPAL_DATA_CONFIG_SOURCES`](/getting-started/configuration#opal_data_config_sources)
when that is set (see [A missing scope](#a-missing-scope) for a 404 instead).

### A missing scope

A scope is missing when its record is not in the scope store: it was never
stored, it was deleted, or the store lost it.
[`OPAL_SCOPES_MISSING_SCOPE`](/getting-started/configuration#opal_scopes_missing_scope)
says what the scope's clients get:

- `default` (the default): `GET /scopes/<scope_id>/policy` serves the policy of
  the scope named `default` (a 404 when that one is not stored either), and
  `GET /scopes/<scope_id>/data` an empty configuration, or the redirect above.
  A client whose scope is lost moves to the `default` scope's policy at its
  next policy fetch.
- `not_found`: both answer 404. An opal-client keeps the policy and data it
  has: after a policy 404 it reports itself unhealthy, and after a data 404 it
  stops polling its entries. Its data connection then reconnects about every
  minute or two and asks again, each time a 404 (with a WARNING and a count),
  until the scope is back; a data update published between two of those
  connections is missed, and the next connect's fetch makes up for it. A client
  that starts while its scope is missing loads no policy until the scope is
  back.

With either, every such request logs a WARNING
(`Requested scope <scope_id> not found, ...`) and counts
`opal_server.scopes.missing_scope`, tagged with the route (`policy` or
`data`). The metric does not say which scope, so that a store that loses many
scopes does not make a series for each: the WARNING names it, and so does the
webhook below.

To have the scope put back, set
[`OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_URL`](/getting-started/configuration#opal_scopes_missing_scope_webhook_url)
to an endpoint of whatever writes the scopes, and
[`OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN`](/getting-started/configuration#opal_scopes_missing_scope_webhook_token)
to the token it expects. A worker that sees a missing scope POSTs

```json
{"scope_id": "internal", "route": "policy", "seen_at": "2026-11-11T09:30:00.000+00:00"}
```

with `Authorization: Bearer` and the token, at most once per scope per 5
minutes, in the background, with a 5-second timeout and no retry; each POST
is counted in `opal_server.scopes.missing_scope_webhook` by outcome. Of the
URL, the server logs only its scheme, host and port. A
`PUT /scopes` of the scope then stores it again and syncs it, and its clients
are told to fetch its policy and data.

`GET /scopes/ids` lists the id of every stored scope, sorted, from the names
of the store's keys, without reading the records as `GET /scopes` does. So a
writer can compare the scopes it expects with the stored ones cheaply. A scope
whose id is `ids` cannot be read with `GET /scopes/<scope_id>`; its other
routes are not affected.

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
(1,000 by default). A policy request with no `base_hash` (a client that holds
no policy yet) first asks every server to fetch the scope's branch, and waits
up to
[`OPAL_SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS`](/getting-started/configuration#opal_scopes_policy_fresh_fetch_wait_seconds)
(10 seconds by default) for this server's fetch.

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

### Readiness and the first clones

By default `/healthcheck` does not look at the scope clones: a new server is
Ready before it has cloned anything, and a policy bundle request for a scope
whose clone has not landed yet cannot be served. To keep a new
server out of service until it can serve its main repositories, list them in
[`OPAL_SCOPES_READY_REQUIRED_REPOS`](/getting-started/configuration#opal_scopes_ready_required_repos),
comma-separated, each URL written exactly as the scopes' policy sources write
it:

```
OPAL_SCOPES_READY_REQUIRED_REPOS=git@github.com:example/policy.git
```

`/healthcheck` then answers `503` until the clone of each has landed, naming the
missing clones' directories, and `200` from then on. With libgit2
(`OPAL_SCOPES_GIT_FETCH_WITH_CLI=false`), the server does not start with this
set unless `OPAL_SCOPES_REPO_CLONES_SHARDS` is 1. Write the URLs without `#`,
quotes or backslashes (percent-encode them): the list is read like a shell word
list, and a server in scopes mode refuses an entry it would change. A URL that no stored
scope's policy source uses is never cloned, so `/healthcheck` stays `503` until
a stored scope uses that URL; the server logs a WARNING naming it (masked) at
the preload and at the leader's sync passes. Each worker remembers the
clones it has seen landed, so a later failed fetch, a remote that is down, or
a clone deleted and cloned again does not take a Ready server out of service.
There is no grace period: allow for the first clones in the deployment's
rollout deadline (`progressDeadlineSeconds` on Kubernetes). Readiness never
restarts the server. `/healthz/started`, for a startup probe, waits for the
same clones, and for a heartbeat of the scopes leader; it answers `200`
from then on (see [health checks](/tutorials/monitoring_opal#health-checks)).

To move probes off scripts that read the clones' `FETCH_HEAD` files, point
the readiness probe at `/healthcheck` with this setting, the startup probe at
`/healthz/started` and the liveness probe at `/healthz/live`. They need no
clone directory names; readiness and startup wait while a required clone is
missing, and none of them fails when a fetch fails. A clone's fetch age moves from the liveness probe to the
`opal_server.scopes.repo_fetch_age_seconds` metric. With
[`OPAL_SCOPES_GIT_RECLONE_HUNG_ON_START`](/getting-started/configuration#opal_scopes_git_reclone_hung_on_start)
on, a start keeps a landed clone of a required repository that a hung git op
marked, where it deletes any other marked clone, so a restart does not wait
for a fresh clone.

### Clones no scope uses

A scope's clone stays in `OPAL_BASE_DIR`'s `git_sources` directory after the
scope stops using it: a scope repointed to another repository, a delete that
reached another server of the deployment but not this one, the shard clones
that the git command line (or a new `OPAL_SCOPES_REPO_CLONES_SHARDS`) leaves
unused, a clone left by a crash. Nothing removes them unless the orphan sweep is
on: set
[`OPAL_SCOPES_ORPHAN_SWEEP_INTERVAL`](/getting-started/configuration#opal_scopes_orphan_sweep_interval)
to the seconds between its looks (it is off by default; 600 is a reasonable
start). The leader worker of each server then looks at its own clones. The
sweep runs with `OPAL_REPO_WATCHER_ENABLED` on only, as the leader's syncs do.

- A clone goes once two looks at least an interval apart found no stored scope
  using it, and none in between found one. The clones of
  `OPAL_SCOPES_READY_REQUIRED_REPOS` always stay, and only real directories
  named like a clone count: never a symlink, the heartbeat file or anything
  else in `OPAL_BASE_DIR`.
- Right before a clone goes, the sweep reads the scope store again (bounded
  by `OPAL_SCOPES_STORE_READ_TIMEOUT`): a scope stored, or repointed back,
  since the look that uses the clone keeps it.
- With it go its lock file, its hung-op markers, the directories a clone of it
  was being made in and the SSH host keys recorded for it: the next clone of
  that repository trusts the key its host shows on first use again (see
  [SSH host keys](#ssh-host-keys)). A clone that a git op, a repack or a delete
  holds is kept for the next look. At most 16 go per look.
- Nothing goes while the store lists no scope at all, or while more than
  [`OPAL_SCOPES_ORPHAN_SWEEP_MAX_SHARE`](/getting-started/configuration#opal_scopes_orphan_sweep_max_share)
  of the clones (half, by default; the required clones not counted) are
  unused. A scope store that was wiped, or a server pointed at another Redis
  database, looks the same as one whose scopes were all deleted, so after a
  wipe the sweep keeps every clone and counts `opal_server.scopes.orphan_sweep`
  with outcome `refused` until the scopes are back. After a refusal a clone
  goes only once two looks in a row found the store no bigger, so a store being
  refilled keeps the clones of the scopes still to come. When the scopes
  really are gone, raise the share to 1.0 (no guard) and restart.
- A scope whose record Redis evicted counts as deleted: its clone goes, and is
  cloned again once the record is back. Scope records have no expiry, so only
  an `allkeys-*` `maxmemory-policy` can evict them; check the scope store's
  policy before turning the sweep on.
- In the clones it keeps, each look also removes the fetch marks
  (`.git/opal-fetched`), of success and of failure, of branches no stored
  scope of the clone tracks, and the temp files a mark writer that died left.

What a look saw lives in the leader's memory: a restart or a new leader starts
over, which delays a removal and never hastens one. The
[metrics](/tutorials/monitoring_opal#scope-git-metrics) count every look and
every clone removed.

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
  them by hand, or turn on the orphan sweep
  ([Clones no scope uses](#clones-no-scope-uses)). A Kubernetes pod on an
  `emptyDir` starts with an empty volume and makes one clone per repository.
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
  scope catches up at that scope's next refresh, the next sync pass, or when a
  client with no policy starts on that scope, not at a fetch for another
  scope. `FETCH_HEAD`'s age is still that of the clone's
  last fetch that succeeded, of whatever branches.
  `OPAL_SCOPES_GIT_CLI_NARROW_FETCH_MAX_BRANCHES=0` makes every fetch fetch
  every branch, as 0.9 did.
- A policy request with no `base_hash` (a client that holds no policy yet)
  now waits up to `OPAL_SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS` (10 seconds)
  for this server's fetch of the scope's branch, and asks every server to
  fetch it; only a fetch that started after the request counts, so while
  clients keep starting each server fetches the branch one fetch after
  another. Any client allowed to read the scope's policy can now make the
  servers fetch. Usually it waits one fetch and a broadcast round trip. When
  that fetch fails or runs past the wait, or the request finds the server at
  its in-flight cap before any fetch of the branch succeeded within the wait,
  a branch the clone does not have is a 503 with Retry-After 5, where 0.9
  answered 409 at once. `OPAL_SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS=0` turns
  the wait off.
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
- A scope's data entries are served and published with their topics as
  `<scope_id>:data:<topic>` (see [A scope's data sources](#a-scopes-data-sources)).
  An entry whose topics were written otherwise, such as the default
  `policy_data`, was dropped by the scope's clients and now loads. A
  `PUT /scopes` that creates a scope or changes its `data` now makes the
  scope's connected clients fetch its entries.
- `GET /scopes/<scope_id>/data` for a scope that is not stored answers an empty
  configuration, where 0.9 served `OPAL_DATA_CONFIG_SOURCES`'s entries (the
  redirect to its `external_source_url` is unchanged).
- `POST /scopes/<scope_id>/data/update` writes its entries' topics as
  `<scope_id>:data:<topic>`, which the scope's clients take, where 0.9 wrote
  `data:<topic>`, which they dropped; a topic already starting with
  `<scope_id>:data:` is kept as it is.
- A request for a missing scope's policy or data now counts
  `opal_server.scopes.missing_scope`, besides its WARNING (see
  [A missing scope](#a-missing-scope)). `OPAL_SCOPES_MISSING_SCOPE` is
  `default`, which answers as 0.9 did, but for the empty data configuration
  above. Set it to `not_found` once whatever writes the scopes puts a lost one
  back (for example from `OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_URL`), so that a
  client whose scope is lost keeps its own policy. A value other than `default`
  or `not_found` stops the server.
- The orphan sweep is new and off: with
  `OPAL_SCOPES_ORPHAN_SWEEP_INTERVAL` unset nothing changes. Turned on, it
  removes the clones no stored scope uses, as above.
- A scope stored with a branch that is a revision rather than a branch name
  (`x~1`, which `PUT /scopes` now refuses) gets no policy and a 409, with
  the missing-branch ERROR on every pass, where 0.9 served the commit the
  revision named. It is not deleted: a `PUT` with a real branch fixes it.

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
