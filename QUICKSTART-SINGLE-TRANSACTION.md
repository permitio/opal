# Quick Start: Testing Fast Cold-Start Mode Locally

This guide shows how to test the `INITIAL_POLICY_LOAD_MODE=single_transaction` feature — OPAL's fast cold-start optimization.

## Prerequisites

- Docker & Docker Compose
- Python 3.8+ (optional, for manual testing)
- Git

---

## ⚡ Quickest Way (Docker Compose)

Everything runs in one command:

```bash
cd /path/to/opal
docker-compose -f docker/docker-compose-example-single-transaction.yml down -v
docker-compose -f docker/docker-compose-example-single-transaction.yml up -d --build
sleep 10
docker-compose -f docker/docker-compose-example-single-transaction.yml logs opal_client | tail -30
```

```bash
# This clears the screen and refreshes the 'logs --tail 20' view every 2 seconds
watch "docker-compose -f docker/docker-compose-example-single-transaction.yml logs --tail 20"
```

**What to look for:**

```
Policy engine is healthy and ready           # OPA started
Got policy bundle with 3 rego files, 2 data files  # Policies fetched from git
Applying full policy bundle atomically       # Single-transaction mode activated
OPA transaction API unavailable, falling back... # (graceful fallback - OK!)
policy_full_load_duration_ms=<value>         # Total load time
```

Done! The stack is running with all policies loaded from the git repository. Access the OPAL client UI at `http://localhost:7766`.

**To stop everything:**
```bash
docker-compose -f docker/docker-compose-example-single-transaction.yml down -v
```

---

## Detailed Setup (for manual testing & development)

### Setup

### 1. Start OPA in standalone server mode

```bash
docker run -d --name opa-local -p 8181:8181 openpolicyagent/opa:1.16.1 run --server --addr :8181
```

Verify OPA is running:

```bash
curl http://localhost:8181/health
# Should return HTTP Status 200 with response: {}
```
```bash
curl http://localhost:8181/v1/config
# Should return HTTP Status 200 with response: {..., "version":"{your version}"}
```
```bash
# tailing the logs
docker logs -f opa-local
```

### 2. Set up a minimal test policy repo

The test directory with 10 rego modules and data.json is ready at the project root: `test-policies/`.

Initialize it as a git repo:

```bash
cd /path/to/opal/test-policies
git init
git add .
git config user.email "test@example.com"
git config user.name "Test User"
git commit -m "Initial policies"
```

### 3. Start OPAL server (pointing to your test repo)

In a new terminal:

```bash
cd /path/to/opal

# Option A: Use docker-compose from the repo
docker-compose -f docker/docker-compose-example.yml up -d

# Option B: Or run the server directly (requires opal-server installed)
# opal-server --policy-repo-url file:///path/to/opal/test-policies
```

If using docker-compose, verify the server is up:

```bash
curl http://localhost:7002/healthcheck
```

---

## Test 1: Default Behavior (per_module)

### Start OPAL client WITHOUT the flag

```bash
cd /path/to/opal/packages/opal-client

OAPL_SERVER_URL=http://localhost:7002 \
POLICY_STORE_URL=http://localhost:8181 \
python -m opal_client.main &
```

Or with explicit default:

```bash
OAPL_SERVER_URL=http://localhost:7002 \
POLICY_STORE_URL=http://localhost:8181 \
OPAL_INITIAL_POLICY_LOAD_MODE=per_module \
python -m opal_client.main &
```

### Observe the output

Watch the logs for:

```
Refetching policy code (full bundle)
Got policy bundle with 10 rego files, 1 data files
# Then you'll see multiple individual PUT calls:
set_policy: policy_1.rego -> 200
set_policy: policy_2.rego -> 200
... (10 separate calls, each triggering OPA compile)
```

**Note the time:** From "Refetching policy code" to the final policy loaded. Check the structured log for `policy_full_load_duration_ms=<value>`.

---

## Test 2: Fast Cold-Start (single_transaction)

### Stop the previous client

```bash
pkill -f "python -m opal_client.main"
```

### Force OPA to forget the policies

```bash
curl -X DELETE http://localhost:8181/v1/policies
# Or restart OPA:
docker restart opa-local
```

### Start OPAL client WITH the flag

```bash
cd /path/to/opal/packages/opal-client

OAPL_SERVER_URL=http://localhost:7002 \
POLICY_STORE_URL=http://localhost:8181 \
OPAL_INITIAL_POLICY_LOAD_MODE=single_transaction \
python -m opal_client.main &
```

### Observe the output

Watch for:

```
Refetching policy code (full bundle)
Got policy bundle with 10 rego files, 1 data files
Applying full policy bundle atomically (mode=single_transaction, rego_files=10, data_files=1, ...)
```

**If OPA supports the transaction API (OPA 0.45.0+), you'll see:**
```
# Then:
POST /v1/transactions -> txn-123
PUT /v1/policies/policy_1.rego?txn=txn-123 -> 200
PUT /v1/policies/policy_2.rego?txn=txn-123 -> 200
... (all in the same transaction)
POST /v1/transactions/txn-123/commit -> 200 (SINGLE COMPILE HERE)
policy_full_load_duration_ms=<value> mode=single_transaction rego_files=10 data_files=1
```

**If the transaction API is unavailable, OPAL automatically falls back to per-module mode:**
```
POST /v1/transactions -> 404
OPA transaction API unavailable, falling back to per-module policy load
# Then loads policies one by one:
PUT /v1/policies/policy_1.rego -> 200
PUT /v1/policies/policy_2.rego -> 200
... (individual PUT calls, each triggering compile)
policy_full_load_duration_ms=<value> mode=per_module rego_files=10 data_files=1
```

Either way, policies load successfully. The single_transaction mode is attempted first and gracefully falls back if needed.

### Verify startup completed successfully

Look for these logs to confirm full startup (in order):

```
policy.updater | INFO | Connected to server
policy.updater | INFO | Refetching policy code (full bundle)
policy.updater | INFO | Got policy bundle with X rego files, Y data files
policy.updater | INFO | Applying full policy bundle atomically (or per-module)
# ... policy load logs ...
policy.updater | INFO | policy_full_load_duration_ms=<value> mode=<mode>
engine.logger | INFO | Sent response -> 200/204  # Last successful policy load
```

The **`policy_full_load_duration_ms`** metric shows the total time from "Got policy bundle" to all policies loaded. This is what you're optimizing with single_transaction mode.

**To manually verify all policies loaded correctly:**
```bash
# Check how many policies are in OPA
curl http://localhost:8181/v1/policies | jq '.result | length'
# Should match the count from the logs (e.g., "10 rego files")

# Verify no policies failed
curl http://localhost:8181/v1/policies | jq '.result | keys'
```

---

## Comparing the two

### Logs to look for

**per_module mode:**
```
policy_full_load_duration_ms=2500 mode=per_module rego_files=10 data_files=1
```

**single_transaction mode:**
```
policy_full_load_duration_ms=350 mode=single_transaction rego_files=10 data_files=1
```

The difference grows with more modules (50+ modules = 10–20x faster).

### Check OPA state

Verify both loaded the same policies:

```bash
curl http://localhost:8181/v1/policies | jq '.result | length'
# Should show 10 (one for each policy_N.rego)
```

---

## Cleanup

**If using docker-compose (quickest way):**
```bash
docker-compose -f docker/docker-compose-example-single-transaction.yml down -v
```

**If using manual setup:**
```bash
# Stop OPAL client
pkill -f "python -m opal_client.main"

# Stop OPA
docker stop opa-local
docker rm opa-local

# Stop OPAL server (if using docker-compose)
docker-compose -f docker/docker-compose-example.yml down
```

---

## Troubleshooting

**OPA transaction API not supported?**

If you see:
```
OPA transaction API unavailable, falling back to per-module policy load
```

This means either:
1. Your OPA version doesn't support `/v1/transactions` (requires OPA 0.45.0+)
2. Your OPA is running with `--v0-compatible` flag (disables v1 API)
3. The transaction API endpoint isn't available for other reasons

**This is not an error** — policies will still load successfully, just using per-module mode instead of atomic transactions. The fallback is automatic and graceful.

To confirm your OPA version supports transactions, check:
```bash
curl http://localhost:8181/v1/transactions -X POST
```

If it returns a transaction ID (not 404), transactions are supported. If using OPAL with inline OPA, ensure `OPAL_OPA_V0_COMPAT=false` is set.

**Can't reach OPAL server?**

```bash
curl http://localhost:7002/healthcheck
```

If it fails, the server may not have started. Check the docker-compose logs:

```bash
docker-compose -f docker/docker-compose-example.yml logs opal-server
```

**Policy repo URL wrong?**

When starting the OPAL server, ensure the `--policy-repo-url` points to your test repo:

```bash
opal-server --policy-repo-url file:///path/to/opal/test-policies
```

Or in docker-compose, set the `OPAL_POLICY_REPO_URL` environment variable.

---

## Next steps

- Increase the number of policies (50+) to see a more dramatic difference
- Add larger rego modules with dependencies to test the retry logic
- Monitor the statistics channel (if enabled) to see the published metrics
- Read [FAST-COLD-START.md](../FAST-COLD-START.md) for more details
