# OPAL git-leak / resilience test bed

Reproduces (as failing tests on `master`) the four issues fixed by PR2–PR5:
memory leak, offline-repo hang, slow serial boot, broadcaster no-reconnect.

## Stack
- `opal_server` (2 workers, scopes on, Postgres broadcaster, built from `docker/Dockerfile`)
- `redis`, `postgres`, `gitea` (+ one-shot `gitea-admin` and `seed` sidecars)

Only `opal_server` (`:7002`) and `gitea` (`:13000` on the host) are published;
Postgres is internal to the compose network.

## Helpers (`helpers.py`)
- `OpalServerClient` — drive opal over HTTP (`stats`, `put_scope`, `delete_scope`, `refresh_all`).
- `GiteaAdmin` — host-side Gitea admin client (`list_repos`, `repo_exists`,
  `create_repo`, `delete_repo`); also exposed as the `gitea_admin` pytest fixture.
- `make_repo_unreachable(name)` — git URL on a routable-but-dead host (TEST-NET-1) for the offline-repo test.
- `bounce_postgres(down_seconds)` — stop/start Postgres to simulate a broadcaster outage.

## Run
```bash
cd app-tests/git-leak
python -m pytest -v --boot-scopes=50              # full set
python -m pytest test_leak.py -v --boot-scopes=20 # just the leak gates
```
Useful flags: `--boot-scopes=N` (any N), `--keep-stack` (skip teardown),
env `BOOT_TARGET_SECONDS=120` (tighten the boot gate).

## Expected on master
The leak tests (#1, #2) and the offline-repo test (#4) FAIL on master — they
target unfixed bugs and become the regression gates for PR2/PR3. The boot test
(#3) passes but only fails when `BOOT_TARGET_SECONDS` is set low (PR4's gate).
The Postgres-bounce test (#5) PASSES on master: it is a recovery guard — when
the broadcaster drops, the worker is respawned by gunicorn while the sibling
worker keeps serving, so the HTTP surface recovers. It guards that property
against regression rather than reproducing a current failure.

## Requires
Docker + docker compose v2, plus host Python with `pytest pytest-timeout requests GitPython`.

## Notes
- Auth is disabled in the stack: `OPAL_AUTH_PUBLIC_KEY` is left unset so the JWT
  verifier is disabled and the harness can call scope routes without minting JWTs.
  Local test bed only; never a production setting.
- The server runs 2 uvicorn workers with a Postgres broadcaster, mirroring a
  realistic multi-worker deployment. The `GitPolicyFetcher` caches read by the
  `/internal/git-fetcher-cache-stats` endpoint are per-process, so the harness
  polls with generous timeouts to let the leader worker converge.
