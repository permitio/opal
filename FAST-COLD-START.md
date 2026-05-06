# Fast Cold-Start Policy Load (single_transaction mode)

## Overview

By default, OPAL client loads a full policy bundle by sending **one HTTP PUT per rego module** to OPA. This causes OPA to recompile its module set on every PUT, resulting in N full recompiles for a repo with N modules before the client is ready to serve.

For large policy repositories (50+ modules), this can add significant latency between "OPAL client started" and "OPA is actually evaluating policies."

The **`INITIAL_POLICY_LOAD_MODE=single_transaction`** setting applies the full bundle inside a **single OPA write transaction**, triggering exactly **one compile** regardless of module count — reducing time-to-readiness dramatically.

## When to use it

**Use `single_transaction` if:**
- Your policy repo has many rego modules (50+) and cold-start latency matters
- You want the initial bundle load (on startup or after a Pub/Sub reconnect) to complete faster
- You're running OPA v0.45.0 or later (supports the transaction API)

**Keep the default `per_module` if:**
- You have a small number of modules (latency isn't a concern)
- You're running a very old OPA version (the feature will automatically fall back)
- You need absolute compatibility with custom OPA deployments

## How to enable it

Set the environment variable:

```bash
OPAL_INITIAL_POLICY_LOAD_MODE=single_transaction
```

Or in your OPAL client config:

```python
from opal_client.policy_store.schemas import InitialPolicyLoadMode
from opal_client.config import opal_client_config

# opal_client_config.INITIAL_POLICY_LOAD_MODE = InitialPolicyLoadMode.SINGLE_TRANSACTION
```

👉 **Quick start:** See [QUICKSTART-SINGLE-TRANSACTION.md](QUICKSTART-SINGLE-TRANSACTION.md) for a local test setup to compare the default vs. fast-start modes.

## How it works

When `INITIAL_POLICY_LOAD_MODE=single_transaction`:

1. **Cold start** (first bundle load): all rego and data modules are written to OPA inside a single write transaction
   - `POST /v1/transactions` → opens a transaction
   - `PUT /v1/policies/<id>?txn=<txn_id>` for each rego module (deferred compile)
   - `PUT /v1/data/<path>?txn=<txn_id>` for each data module (deferred compile)
   - `POST /v1/transactions/<txn_id>/commit` → single compile, one atomic activation

2. **Reconnect-triggered full reload**: same atomic apply (after a Pub/Sub drop/reconnect that forces a full re-fetch)

3. **Delta (patched) updates**: always use the existing per-module path — no change to the steady-state hot path

4. **Fallback**: If OPA doesn't support the transaction API (detected at runtime), the client automatically falls back to `per_module` and logs a warning once

## Expected improvements

On a test repo with 50+ rego modules:

| Setting | Time-to-ready |
|---|---|
| `per_module` (default) | ~15–30s (50+ OPA recompiles) |
| `single_transaction` | ~2–5s (1 OPA compile) |

Your mileage varies based on module count, module size, and OPA hardware.

## Observability

Each full-bundle load emits:

- **Structured log**: `policy_full_load_duration_ms=<int> mode=<per_module|single_transaction> rego_files=<N> data_files=<M>`
- **Statistics event** (if `STATISTICS_ENABLED=true`): sent to the OPAL server's statistics channel with duration and mode
- **Health endpoint** (if supported): last full-load duration visible in client `/healthy` or status payload

Monitor these to validate the performance improvement in your environment.

## Compatibility

- **OPA**: v0.45.0+ (transaction API). Older versions automatically fall back to `per_module`.
- **Cedar**: no effect (Cedar has no per-module compile cost). Works transparently.
- **Custom policy engines**: if they don't support transactions, they fall back automatically.
- **Backward compatibility**: default is `per_module`, so existing deployments are unaffected unless explicitly opted in.

## Troubleshooting

**Q: I enabled `single_transaction` but it's still slow.**

A: Check the logs for a warning about the transaction API being unavailable. The fallback to `per_module` is automatic; if that happens, your OPA version may not support `/v1/transactions`. Verify OPA >= 0.45.0.

**Q: Delta updates (Pub/Sub patches) are still slow.**

A: This setting only optimizes full-bundle loads (cold start + reconnect). Delta updates always use the existing per-module path. If delta performance is a concern, please file an issue.

**Q: Will this become the default?**

A: No. The default will remain `per_module` for maximum compatibility and predictability. Operators must explicitly opt in if they want the single-transaction mode.

## See also

- [OPAL documentation](https://docs.opal.ac)
- [OPA transaction API](https://www.openpolicyagent.org/docs/latest/rest-api/#transactions)
- [OPAL architecture](https://docs.opal.ac/overview/architecture)
