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
The churn leak test (`test_churn_releases_caches`) and the offline-repo test
FAIL on this branch *without the PR2/PR3 fix* — they target unfixed bugs and
become the regression gates for PR2/PR3, flipping green when those land. The
boot test passes but fails when `BOOT_TARGET_SECONDS` is set low (PR4's gate).

Two tests are guards that PASS rather than reproducing a current failure:
- `test_repeat_sync_does_not_grow` — clone paths are keyed by the repo URL, so
  re-syncing identical scopes reuses cache entries and the cache *counts* can't
  grow for any implementation; the load-bearing assertion is therefore on RSS,
  guarding against a regression that leaks per-sync allocations.
- `test_server_recovers_after_postgres_bounce` — when the broadcaster drops, the
  worker is respawned by gunicorn and the broadcaster reconnects once Postgres
  is back; the test PUTs a fresh scope post-bounce and asserts it syncs, proving
  the broadcast path (not just HTTP) recovered.

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
