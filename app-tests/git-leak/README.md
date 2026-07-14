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
- `bounce_postgres(down_seconds, during=None)` — stop Postgres, optionally run a
  callback while it is down (the bounce test publishes a scope mid-outage), then
  `up -d --wait` it back to simulate a broadcaster outage and await readiness
  before the recovery poll.

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
| `test_scope_repoint_releases_old_repo_cache` | **gate (PR2, update path)** | FAILS without PR2 — re-pointing a scope to a new URL orphans the old URL's cache entries; stays red after PR2 unless its purge also covers scope *updates*, not just deletes |
| `test_shared_repo_survives_sibling_scope_delete` | **over-purge guard (PR2)** | PASSES here (nothing purges on master); once PR2 lands it guards against purging a URL-keyed entry that a surviving sibling scope still references |
| `test_offline_repo_does_not_block_healthy_scopes` | **gate (PR3)** | FAILS without the PR3 fetch timeout — 40 hung clones starve the executor so a healthy scope never serves; flips green when PR3 lands |
| `test_boot_loads_all_scopes` | **baseline → gate (PR4)** | PASSES with the loose default target; set `BOOT_TARGET_SECONDS` low (plan: 120 @ 50) on PR4 to gate the parallel-boot fix |
| `test_repeat_sync_rss_stays_bounded` | **RSS guard** | PASSES; an RSS-budget guard against per-sync allocation leaks (the cache *count* can't grow for any impl, so there is no count assertion — see below) |
| `test_server_recovers_after_postgres_bounce` | **guard (PER-15065 + gap publishes)** | PASSES on this branch (which has #915); guards the in-place broadcaster reconnect and that a scope PUT *during* the outage is buffered/replayed, not dropped |
| `test_delete_recreate_storm` | **guard (lock re-mint)** | PASSES — rapid delete/re-create of the same source serializes on the repo lock and ends with clean caches; guards 89e090be |
| `test_randomized_churn_holds_invariants` | **guard (seeded churn)** | PASSES — seeded random put/refresh/settled-delete churn holds invariants at every settle point (replay a failure with `CHURN_SEED=<seed>`); repoints and delete-vs-inflight-sync races are deliberately excluded, both lifted when PR3's fleet purge lands |
| `test_delete_during_hung_fetch_no_crash` | **guard (use-after-free)** | PASSES — deleting a scope whose clone is hung never crashes a worker; guards the use-after-free class 89e090be fixed |
| `test_delete_during_hung_fetch_returns_bounded` | **gate (PR3)** | FAILS without the PR3 fetch timeout — the purge waits on the repo lock and a hung clone holds that lock indefinitely, so the DELETE never returns in bounded time |
| `test_repoint_during_inflight_fetch_drains_old_source` | **gate (PR3, update path)** | Green half passes today — repointing while the old source's clone is hung still serves the new source; red half FAILS without PR3's update-path purge — the old source's cache entries never drain |
| `test_multiworker_churn_drains_every_worker` | **gate (PR3, broadcast)** | FAILS without PR3's broadcast purge — cache purges are process-local, so a worker whose caches were populated by something other than the DELETE it served (e.g. the leader's watcher syncs) leaks permanently; the HIGH finding from the PR2 review, as a gate |
| `test_warm_boot_reuses_clones` | **guard (S2)** | PASSES — a restart with intact clones must serve without re-cloning |
| `test_corrupt_clone_recovers_without_clone_loop` | **guard (S3/T7)** | PASSES — emptying a clone's object store in place while the server holds a warm cached handle is detected as invalid and recovers through the invalid-repo branch with exactly one re-clone, no serve-500s wedge and no re-clone loop; verifies the gutted-object-store detection fix |
| `test_orphan_clone_dir_is_reclaimed` | **gate (orphan sweep, unowned)** | FAILS — a clone dir with no live scope is never reclaimed; no orphan sweep exists yet (PR3+, currently unowned) |
| `test_redis_wiped_boot_reclaims_clones` | **gate (orphan sweep, unowned)** | FAILS — after a scope-store wipe, on-disk clones referencing nothing are never reclaimed; same missing-sweep class as the orphan-dir gate |
| `test_boot_with_unreachable_remotes_still_serves_healthy` | **gate (PR3) — watch this flip** | FAILS without the PR3 fetch timeout — unreachable remotes present at boot hang the preload/first-sync clones and starve the executor, so a healthy scope can't serve; boot-time cousin of the offline gate |
| `test_shard_reconfig_still_serves_but_orphans_old_clones` | **half-gate (S5, orphan sweep)** | Green half PASSES — serving survives a `SCOPES_REPO_CLONES_SHARDS` reconfig (re-clone under new ids); red half FAILS — the old-shard dirs are orphaned until the orphan sweep lands |
| `test_force_push_rewrite_recovers` | **characterization** | PASSES — a force-pushed (rewritten) head is picked up on refresh, pinning today's behavior (pygit2's forced default fetch refspec plus `set_target` moving the local ref) |
| `test_deleted_branch_keeps_serving_last_head` | **characterization** | PASSES — deleting the tracked branch upstream doesn't crash anything; fetch doesn't prune, so OPAL silently keeps serving the last known head (documented, not necessarily desirable, behavior) |

## Invariants
`invariants.py` defines quiescence invariants I1-I6, checked at every `opal`-fixture
teardown (I1-I4 and I6 via `check_invariants`; I5 lives directly in `conftest.py`,
since it needs the worker pids captured at fixture setup): I1 no orphan clone dir on
disk, I2 no cached repo handle with no dir on disk, I3 no `repos_last_fetched` key
with no live scope, I4 no `repo_locks` key with no live scope, I5 the worker pid set
is unchanged across the test (proving no crash/respawn), I6 the scopes API still
answers 200. Two markers let a test opt out deliberately instead of by accident:
`@pytest.mark.invariant_exempt("I1", ...)` for red-gate tests that knowingly leave a
violation behind (named per test, not a blanket skip), and
`@pytest.mark.allow_worker_restart` for tests that restart `opal_server` on purpose,
which would otherwise trip I5.

Notes on the guards:
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
  behaviour) — that a scope PUT after the bounce becomes servable, proving
  the broadcast/sync path recovered (not just HTTP), and that a scope PUT
  *during* the outage becomes servable too: its sync trigger rides the
  git-webhook topic, which the reconnecting broadcaster buffers and replays on
  reconnect (and which #933's publish freeze exempts on master), so a 201
  acknowledged mid-gap must never be silently dropped.
- `test_shared_repo_survives_sibling_scope_delete` — the caches are keyed by
  repo URL, not scope id, so it green-guards PR2 against purging an entry that
  another live scope still references (churn only covers the all-scopes-gone
  direction).

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
