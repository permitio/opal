# OPAL git-leak / resilience test bed

Reproduces (as failing tests on `master`) the four issues fixed by PR2–PR5:
memory leak, offline-repo hang, slow serial boot, broadcaster no-reconnect.

## Stack
- `opal_server` (2 workers, scopes on, Postgres broadcaster, built from `docker/Dockerfile`)
- `redis`, `postgres`, `gitea` (+ one-shot `gitea-admin` and `seed` sidecars)

## Run
```bash
cd app-tests/git-leak
python -m pytest -v --boot-scopes=50              # full set
python -m pytest test_leak.py -v --boot-scopes=20 # just the leak gates
```
Useful flags: `--boot-scopes=N` (any N), `--keep-stack` (skip teardown),
env `BOOT_TARGET_SECONDS=120` (tighten the boot gate).

## Expected on master
All five flagship tests FAIL (except the boot test, which only fails when
`BOOT_TARGET_SECONDS` is set low). They become the regression gates for the fixes.

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
