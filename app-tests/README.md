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
