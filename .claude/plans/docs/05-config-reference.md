# 05 — OPAL Config Reference (private)

Private, internal supplement to the public operator docs under `documentation/docs/`. Tracks
`OPAL_*` env vars added or clarified by the OPAL Server Git Fixes work, with the declaring
`file:line` so contributors can jump straight to the `Confi` declaration. Each key maps to an
`OPAL_<NAME>` env var (the `OPAL_` prefix is added once by the component's `Confi(prefix="OPAL_")`
instantiation — the bare name is what appears in the table).

## 4. opal-server keys

| Env var | Type | Default | Purpose | Declared at |
|---|---|---|---|---|
| `OPAL_SCOPES_GIT_FETCH_TIMEOUT` | float (seconds) | `120.0` | Hard timeout for a single scope git clone/fetch. On timeout the operation is logged and skipped (retried next cycle), so one unreachable repo can never block boot or other scopes *indefinitely*. `0` = no timeout. | `packages/opal-server/opal_server/config.py:214-221` |
| `OPAL_SCOPES_GIT_MAX_WORKERS` | int | `10` | Bounds how many scope git operations (clone/fetch) may be *LIVE* (not yet timed out) at once, via an `asyncio.Semaphore` — there is no shared thread pool. Each operation still gets its own single-use daemon-thread executor, so a timed-out operation releases its capacity slot immediately rather than waiting for its thread to die; also bounds how many scopes are synced concurrently. | `packages/opal-server/opal_server/config.py:222-226` |
| `OPAL_SCOPES_PURGE_CHANNEL` | str | `__opal_scope_purge__` | fleet-wide scope purge channel | `packages/opal-server/opal_server/config.py:311-318` |

> **Caveat (timeout is soft, not a hard kill).** `OPAL_SCOPES_GIT_FETCH_TIMEOUT` is enforced via
> `asyncio.wait`, which unblocks the event loop and the awaiting coroutine — but the underlying
> pygit2 call keeps running on its own private daemon-thread executor until the OS network timeout
> fires (a "zombie"). There is no shared pool for these zombies to exhaust: each git operation gets a
> single-use `_DaemonThreadPoolExecutor(max_workers=1)`, so a lingering op occupies only its own
> thread and never holds capacity another operation needs. A per-repo in-flight guard
> (`git_op_in_flight`) prevents a second git op from touching the same (non-thread-safe) pygit2 repo
> while the first is still lingering. Hard-kill via subprocess is out of scope. See spec §6.
>
> **Boot / concurrency.** Scope syncs run concurrently, bounded by `OPAL_SCOPES_GIT_MAX_WORKERS` via
> an asyncio semaphore that gates only LIVE (not-yet-timed-out) operations. On timeout, the awaiting
> coroutine unblocks *and* its semaphore slot is released immediately — before the zombie thread
> returns — so a queued op waits for a freed **slot**, not a freed thread. That makes
> `ceil(offline / workers) × timeout` the correct worst-case bound for how long a healthy scope waits
> before it can start; `OPAL_SCOPES_GIT_FETCH_TIMEOUT` should be set well below any deployment's
> acceptable serve latency. What the worker count does *not* bound is the zombie count: with `N`
> sources unreachable and `M` live slots, worst-case thread count during an outage is `M` (live) plus
> up to `N` (lingering zombies, each alive until its own OS/TCP network timeout — which can far exceed
> `OPAL_SCOPES_GIT_FETCH_TIMEOUT`). (This bears on the `app-tests/git-leak` offline test, which runs
> 40 offline repos against the default 10 workers.)
>
> **What this actually guarantees.** (1) **event-loop isolation** — the HTTP surface and bundle
> serving run on the loop's default executor, never a git operation's thread, so they never block on a
> hung repo; (2) a **bounded per-slot stall** — each sync's coroutine waits at most
> `OPAL_SCOPES_GIT_FETCH_TIMEOUT` before the event loop moves on and its capacity slot is freed for
> the next queued operation; and (3) **daemon threads** — every operation's private executor thread is
> a daemon thread, so a lingering zombie never blocks process shutdown, however many are outstanding.
