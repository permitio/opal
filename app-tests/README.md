# OPAL E2E Tests

A pytest suite that runs a fleet of OPAL servers and clients with docker compose and checks
what the fleet does: policy and data updates reach every client, the statistics count the
fleet, and the fleet recovers from broadcaster outages without splitting.

The stack (`docker-compose-app-tests.yml`):
- a Gitea server that hosts the policy repository, so the suite needs no secret and no
  network
- two OPAL server replicas, on a PostgreSQL broadcast channel
- two OPAL client replicas
- the policy files from `opal-tests-policy-repo-main/`

`git-leak/` is a separate suite for scopes and the git fetchers, with its own stack and README.

## Prerequisites

- Docker with Docker Compose v2
- git and ssh-keygen
- Python 3.14, with this directory's requirements:
  `python -m pip install --require-hashes -r requirements.txt`

## Running the Tests

Build the images under test, then run pytest from this directory:

```bash
docker build -f docker/Dockerfile --target server -t permitio/opal-server:test .
docker build -f docker/Dockerfile --target client -t permitio/opal-client:test .
cd app-tests
OPAL_IMAGE_TAG=test python -m pytest
```

Without `OPAL_IMAGE_TAG`, compose pulls the `latest` images from Docker Hub.

The suite brings the stack up once, runs the tests in `test_fleet.py` in file order (the
broadcaster outages last), and takes it down with its volumes. The stack publishes its ports
on free loopback ports, so it runs beside other stacks; to run two copies of the suite at once,
give each its own `COMPOSE_PROJECT_NAME`. When a test fails, the run ends with the stack's
logs.

## The GitHub lane

CI runs the tests marked `policy_repo` a second time with the policy repository on github.com
over SSH (`docker-compose-github.yml`), the way most deployments fetch their policy:

```bash
OPAL_TESTS_POLICY_REPO_DEPLOY_KEY="$(cat deploy_key)" OPAL_IMAGE_TAG=test \
  python -m pytest --policy-repo=github -m policy_repo
```

It pushes a `test-*` branch to `permitio/opal-tests-policy-repo` and deletes it at the end, so
it needs a deploy key with write access. CI runs it in its own workflow, `e2e-github.yml`, only
when the key's secret is there (never for pull requests from forks), and not as a required
check: a missing or revoked key fails that workflow and blocks nothing.

## Running a mixed-version fleet

By default the client and server use the same image tag, so a run tests one
version against itself. `OPAL_CLIENT_IMAGE_TAG` overrides the client
independently:

```bash
# a released client against a server built from this tree
docker build -f docker/Dockerfile --target server -t permitio/opal-server:test .
OPAL_IMAGE_TAG=test OPAL_CLIENT_IMAGE_TAG=0.9.6 python -m pytest
```

This matters because **opal-client is customer-deployed and upgrades on its own
schedule**. A server-side change therefore has to keep working against clients
that are several releases behind - that is the steady state in the field, not a
transient rollout window. Running both sides from the same commit cannot see a
break there.

It is the check to run whenever a change touches a payload that crosses the
wire: `DataUpdate`, `DataSourceConfig`, `PolicyBundle`, `DataUpdateReport`. The
serialization half of the same contract is pinned in
`packages/opal-common/opal_common/tests/wire_compat/`, which runs in CI; this
covers the behaviour the wire format alone cannot.

## From run.sh

The suite replaced `run.sh`. Each of its functions maps to a test, a fixture or a helper here
(`stack.py`, `conftest.py`, `test_fleet.py`):

| run.sh | pytest |
|---|---|
| `generate_opal_keys` | `auth` fixture (`stack.create_auth`): a passphrase-protected RSA key pair, and a client and a data source token from `/token` on a standalone server of the image under test |
| `prepare_policy_repo` | `policy_repo` fixture: `Gitea.create_admin`, `Gitea.create_policy_repo` (the policy files on `main` and on a `test-*` branch the servers track) |
| `compose` | `stack.Compose` |
| `check_clients_logged` for "Connected to PubSub server", "Got policy bundle" and "PUT /v1/data/static -> 204" | `fleet` fixture: the stack is up once each client has logged all three |
| `check_no_error` | `test_no_client_logs_an_error_at_startup` |
| `check_clients_logged` | `Fleet.wait_for_each_client` |
| `check_servers_logged`, `wait_for_servers_logged` | `Fleet.wait_for_servers` |
| `check_servers_not_logged`, `check_clients_not_logged` | `Fleet.assert_not_logged` (fails on empty logs, as they did) |
| `count_backbone_drops`, `wait_for_backbone_drop` | `Fleet.worker_counts`, `Fleet.wait_for_every_listener` |
| `wait_for_broadcaster` | `Fleet.wait_for_broadcaster` |
| `test_push_policy` | `push_and_expect`; `test_a_pushed_policy_reaches_every_client` |
| `publish_data`, `test_data_publish` | `Fleet.publish_data`, `publish_and_expect`; `test_a_data_update_reaches_every_client` |
| `test_statistics` | `test_every_server_counts_two_servers_and_two_clients` |
| `main`: graceful restart of the broadcast channel | `test_updates_reach_every_client_after_a_broadcaster_restart` |
| `main`: ungraceful kill, then the reconnect and `list.remove(x)` guards | `test_updates_reach_every_client_after_the_broadcaster_is_killed` |
| `main`: cross-instance consistency across a backbone outage | `test_the_fleet_stays_consistent_across_a_backbone_outage` |
| `clean_up` | `compose` fixture: `down --volumes` before and after the run, the logs after a failed one |
| the retry loop (up to 5 attempts) | none: each step waits for the state it needs |

Where the suite checks more than `run.sh` did:
- It waits for states instead of sleeping. After a broadcaster outage, it publishes once every
  server worker has resynced its clients and they have reconnected; during an outage, once
  every worker has seen the channel drop, not only the first. That is why it needs no retries.
- The statistics check fails when a server reports other counts. In `run.sh` its `grep` could
  not fail the run.
- The outage checks look only at lines logged during their own outage, not at the whole run:
  every worker reconnects after the kill, and the buffering of internal topics happens during
  the consistency outage, before the channel comes back.
- A data update fetches the servers' own `/policy-data` route, not a third-party API, so no
  update leaves the stack, and none fetches over HTTPS.
  `test_each_client_trusts_a_full_ca_bundle` checks instead, with no network, that each client's
  default SSL context, the one its HTTPS fetches use, loads the image's CA bundle.
- The startup check for client errors waits until both clients have reported their first
  data update to a server, then watches for 15 s, the window `run.sh` gave it.

## Test Policy Files

The test policies are stored in `opal-tests-policy-repo-main/` and include:
- `rbac.rego` - Role-based access control policies
- `utils.rego` - Utility functions
- `policy.cedar` - Cedar policy examples
- `data.json` - Initial data
- `.manifest` - Repository manifest

## Troubleshooting

The logs of a failed run are at its end. To look at a stack yourself, use the suite's compose
project (`COMPOSE_PROJECT_NAME`, by default `app-tests`):

```bash
docker compose -f docker-compose-app-tests.yml ps
docker compose -f docker-compose-app-tests.yml logs opal_server
docker compose -f docker-compose-app-tests.yml down --volumes
```
