import os
import time

import pytest
import requests
from helpers import compose, gitea_repo_url, list_seeded_repos


@pytest.mark.timeout(2400)
def test_boot_loads_all_scopes(opal, repo_count):
    """Measure how long a fresh boot takes to *serve* all scope repos.

    On master boot-sync is serial and slow (the ~20-min problem at scale). PR1
    records the baseline (loose target, so it passes here as a baseline
    recorder); PR4 (boot parallelism) is what makes this a hard gate.

    Carry-forward for PR4: run with a tight ``BOOT_TARGET_SECONDS`` (the plan:
    120s @ 50 scopes) so the assertion actually gates the parallel-boot fix —
    with the default loose target it always passes and only records a number.

    Completion is keyed on every scope's bundle being *served*
    (``GET /scopes/{id}/policy`` == 200), not on the ``repo_locks`` cache count:
    ``repo_locks`` is set at fetch *start*, so stopping the clock on it would end
    before the final clone finishes and undercount the boot-sync window this gate
    exists to measure.
    """
    n = repo_count
    repos = list_seeded_repos(n)
    scope_ids = [f"boot-{i}" for i in range(n)]
    for scope_id, name in zip(scope_ids, repos):
        opal.put_scope(scope_id, gitea_repo_url(name))

    # Start the clock at the restart, not after wait_healthy: preload_scopes()
    # runs in gunicorn's `when_ready` (before workers accept traffic), so by the
    # time /healthcheck answers, boot-sync may already be partly done — starting
    # the clock later would undercount it. (Clones survive a restart, so preload
    # re-discovers the on-disk repos rather than re-cloning from scratch.)
    start = time.time()
    compose("restart", "opal_server")
    opal.wait_healthy(timeout=600)

    # Poll until every scope serves its bundle. Re-check only the not-yet-served
    # ones so the work drains as scopes come online; a not-yet-cloned scope
    # returns a non-200 quickly (it does not block), so this stays cheap.
    served = set()
    poll_deadline = time.time() + 1800
    while time.time() < poll_deadline:
        for scope_id in scope_ids:
            if scope_id in served:
                continue
            try:
                if opal.get_scope_policy(scope_id).status_code == 200:
                    served.add(scope_id)
            except requests.RequestException:
                pass
        if len(served) == n:
            break
        time.sleep(2)
    elapsed = time.time() - start

    BOOT_TARGET_SECONDS = int(os.environ.get("BOOT_TARGET_SECONDS", "2000"))
    print(
        f"boot served {len(served)}/{n} scopes in {elapsed:.1f}s "
        f"(target {BOOT_TARGET_SECONDS}s)"
    )
    assert len(served) == n, f"only {len(served)}/{n} scopes served after boot"
    assert elapsed < BOOT_TARGET_SECONDS, f"boot too slow: {elapsed:.1f}s"
