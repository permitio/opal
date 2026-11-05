# OPAL E2E Tests

This directory contains end-to-end tests for OPAL using a local Gitea git server instead of relying on external services like GitHub.

## Overview

The tests spin up a complete OPAL environment including:
- A local Gitea git server to host the policy repository
- Multiple OPAL server instances (2 replicas)
- Multiple OPAL client instances (2 replicas)
- A PostgreSQL database for broadcast communication
- Policy files loaded from `opal-tests-policy-repo-main/`

## Prerequisites

- Docker and Docker Compose
- Bash shell
- Basic Unix tools (curl, git, openssl, ssh-keygen)

## Running the Tests

Simply run:
```bash
./run.sh
```

The script will:
1. Generate authentication keys and tokens
2. Start a local Gitea server
3. Create a test repository with initial policy files
4. Start OPAL servers and clients
5. Run various tests including:
   - Policy updates via git push
   - Data updates via API
   - Statistics verification
   - Broadcast channel disconnection handling

## Running a mixed-version fleet

By default the client and server use the same image tag, so a run tests one
version against itself. `OPAL_CLIENT_IMAGE_TAG` overrides the client
independently:

```bash
# a released client against a server built from this tree
docker build -f docker/Dockerfile --target server -t permitio/opal-server:test .
OPAL_IMAGE_TAG=test OPAL_CLIENT_IMAGE_TAG=0.9.6 ./run.sh
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

Note `run.sh` retries up to 5 times. The broadcaster-reconnect assertions after
the *ungraceful* kill are timing-sensitive and can need a retry on a slow
machine, independently of which images are in play - so judge a run by its final
verdict, not by whether attempt 1 passed.

## Test Policy Files

The test policies are stored in `opal-tests-policy-repo-main/` and include:
- `rbac.rego` - Role-based access control policies
- `utils.rego` - Utility functions
- `policy.cedar` - Cedar policy examples
- `data.json` - Initial data
- `.manifest` - Repository manifest

## Troubleshooting

If tests fail:
1. Check Docker logs: `docker compose -f docker-compose-app-tests.yml logs`
2. Ensure ports 3000, 7002-7003, 7766-7767, 8181-8182 are available
3. Clean up and retry: `docker compose -f docker-compose-app-tests.yml down -v`

The script automatically retries up to 5 times to handle transient failures.

## Cleanup

The script automatically cleans up all resources on exit. Manual cleanup:
```bash
docker compose -f docker-compose-app-tests.yml down -v
rm -rf opal-tests-policy-repo temp-repo gitea-data git-repos .env
```
