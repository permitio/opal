# 05 — OPAL Config Reference (private)

Private, internal supplement to the public operator docs under `documentation/docs/`. Tracks
`OPAL_*` env vars added or clarified by the OPAL Server Git Fixes work, with the declaring
`file:line` so contributors can jump straight to the `Confi` declaration. Each key maps to an
`OPAL_<NAME>` env var (the `OPAL_` prefix is added once by the component's `Confi(prefix="OPAL_")`
instantiation — the bare name is what appears in the table).

## 4. opal-server keys

| Env var | Type | Default | Purpose | Declared at |
|---|---|---|---|---|
| `OPAL_SCOPES_GIT_FETCH_TIMEOUT` | float (seconds) | `120.0` | Hard timeout for a single scope git clone/fetch. On timeout the operation is abandoned and the scope is marked failed, so one unreachable repo can never block boot or other scopes. `0` = no timeout. | `packages/opal-server/opal_server/config.py:150-156` |
| `OPAL_SCOPES_GIT_MAX_WORKERS` | int | `10` | Size of the dedicated `ThreadPoolExecutor` for scope git operations. Isolating git work keeps a hung fetch from starving bundle serving and other server work that uses the default executor. | `packages/opal-server/opal_server/config.py:157-163` |

> **Caveat (timeout is soft, not a hard kill).** `OPAL_SCOPES_GIT_FETCH_TIMEOUT` is enforced via
> `asyncio.wait_for`, which cancels the *await* — unblocking the event loop and the awaiting
> coroutine — but the underlying pygit2 call keeps running on its pool thread until the OS network
> timeout. The dedicated pool (`OPAL_SCOPES_GIT_MAX_WORKERS`) bounds and isolates those lingering
> threads so they cannot affect bundle serving or other scopes. Hard-kill via subprocess is out of
> scope. See spec §6.
