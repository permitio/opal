# OPAL git-leak / resilience test bed

Reproduces (as failing tests) the four issues fixed by PR2–PR5: memory leak,
offline-repo hang, slow serial boot, broadcaster no-reconnect.

Every assertion is driven through `GET /internal/git-fetcher-cache-stats`, which
**this PR (PR1) adds** — it does not exist on `master`. So the suite runs against
*this branch*: the leak/offline tests fail here *until PR2/PR3 land*, then go
green. Run against true `master` they would all error at setup on the missing
endpoint, not "fail for the targeted bug."

## Stack
- `opal_server` (single worker, scopes on, Postgres broadcaster, built from `docker/Dockerfile`)
- `redis`, `postgres`, `gitea` (+ one-shot `gitea-admin` and `seed` sidecars)
- `blackhole` (alpine/socat: accepts TCP then never answers — the offline repo)

Only `opal_server` (`:7002`) and `gitea` (`:13000` on the host) are published;
Postgres and `blackhole` are internal to the compose network.

## Helpers (`helpers.py`)
- `OpalServerClient` — drive opal over HTTP (`stats`, `put_scope`, `delete_scope`,
  `refresh_all`, `get_scope_policy`, `list_scope_ids`, `delete_all_scopes`).
- `GiteaAdmin` — host-side Gitea admin client (`list_repos`, `repo_exists`,
  `create_repo`, `delete_repo`); also exposed as the `gitea_admin` pytest fixture.
- `make_repo_unreachable(name)` — git URL on the `blackhole` sidecar (completes
  the TCP handshake, never answers) so the clone hangs for the offline-repo test.
- `bounce_postgres(down_seconds)` — stop Postgres, then `up -d --wait` it back to
  simulate a broadcaster outage and await readiness before the recovery poll.

## Run
```bash
cd app-tests/git-leak
python -m pytest -v --boot-scopes=50              # full set
python -m pytest test_leak.py -v --boot-scopes=20 # just the leak gates
```
Useful flags: `--boot-scopes=N` (any N), `--keep-stack` (skip teardown),
env `BOOT_TARGET_SECONDS=120` (tighten the boot gate).

## Expected behavior

Gate-coverage matrix (what each flagship test actually does):

| Test | Role | Behaviour here |
|---|---|---|
| `test_churn_releases_caches` | **gate (PR2)** | FAILS without the PR2 leak fix — delete leaves the caches populated; flips green when PR2 lands |
| `test_offline_repo_does_not_block_healthy_scopes` | **gate (PR3)** | FAILS without the PR3 fetch timeout — 40 hung clones starve the executor so a healthy scope never serves; flips green when PR3 lands |
| `test_boot_loads_all_scopes` | **baseline → gate (PR4)** | PASSES with the loose default target; set `BOOT_TARGET_SECONDS` low (plan: 120 @ 50) on PR4 to gate the parallel-boot fix |
| `test_repeat_sync_rss_stays_bounded` | **RSS guard** | PASSES; an RSS-budget guard against per-sync allocation leaks (the cache *count* can't grow for any impl, so there is no count assertion — see below) |
| `test_server_recovers_after_postgres_bounce` | **guard (PER-15065)** | PASSES on this branch (which has #915); guards the in-place broadcaster reconnect |

Notes on the two guards:
- `test_repeat_sync_rss_stays_bounded` — clone paths are keyed by the repo URL,
  so re-syncing identical scopes reuses cache entries and the cache *counts*
  can't grow for any implementation; the load-bearing assertion is therefore on
  RSS only (a `len(repos)` check would be tautological and is intentionally
  omitted), guarding against a regression that leaks per-sync allocations.
- `test_server_recovers_after_postgres_bounce` — runs **2 workers** so the
  Postgres backbone is actually exercised (cross-worker fan-out needs >=2
  workers; a single worker fans out in-process and never touches the backbone).
  Across a transient bounce it asserts the gunicorn **worker PIDs are unchanged**
  — proving #915's reconnecting broadcaster recovered the reader *in place*
  rather than gunicorn respawning a graceful-shutdown worker (the pre-fix
  behaviour) — and that a scope PUT after the bounce becomes servable, proving
  the broadcast/sync path recovered (not just HTTP).

## Requires
Docker + docker compose v2, plus host Python with `pytest pytest-timeout requests GitPython`.

## Notes
- Auth is disabled in the stack: `OPAL_AUTH_PUBLIC_KEY` is left unset so the JWT
  verifier is disabled and the harness can call scope routes without minting JWTs.
  Local test bed only; never a production setting. (The `/internal` endpoint is
  registered with the same `JWTAuthenticator` dependency as the other routes, so
  it is protected when JWT verification is enabled and open only here.)
- The server runs a **single** uvicorn worker. The `GitPolicyFetcher` caches read
  by `/internal/git-fetcher-cache-stats` are per-process, so a multi-worker stack
  would make a round-robin read miss the worker that fetched and let a `== 0`
  drain assertion pass falsely. One worker makes every cache read deterministic;
  the leak/boot/offline bugs all reproduce single-worker.
- First-sync of a fresh scope takes the clone path, which fills only `repo_locks`;
  `repos` / `repos_last_fetched` are filled by the discover/fetch path on a second
  sync, so the load helpers issue a `refresh_all()` before asserting on `repos`.
