import asyncio
import math
import os
import pathlib
import time
from collections import OrderedDict
from functools import partial
from typing import Awaitable, Callable, List, Optional, Set, Tuple, cast

import pygit2
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse
from fastapi_websocket_pubsub import PubSubEndpoint
from git import InvalidGitRepositoryError, NoSuchPathError
from opal_common.async_utils import run_sync
from opal_common.authentication.authz import (
    require_peer_type,
    restrict_optional_topics_to_publish,
)
from opal_common.authentication.casting import cast_private_key
from opal_common.authentication.deps import JWTAuthenticator, get_token_from_header
from opal_common.authentication.types import EncryptionKeyFormat, JWTClaims
from opal_common.authentication.verifier import Unauthorized
from opal_common.http_utils import redact_url_in_text
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.data import (
    DataSourceConfig,
    DataUpdate,
    ServerDataSourceConfig,
)
from opal_common.schemas.policy import PolicyBundle, PolicyUpdateMessageNotification
from opal_common.schemas.policy_source import GitPolicyScopeSource, SSHAuthData
from opal_common.schemas.scopes import Scope
from opal_common.schemas.security import PeerType
from opal_common.topics.publisher import ServerSideTopicPublisher
from opal_common.urls import set_url_query_param
from opal_server.config import opal_server_config
from opal_server.data.data_update_publisher import DataUpdatePublisher
from opal_server.git_cli import clone_under_way, drop_clone_lock, take_clone_lock
from opal_server.git_fetcher import (
    BranchHeadNotFoundError,
    BranchHeadObjectMissingError,
    CloneNotPopulatedError,
    GitPolicyFetcher,
    clone_landed,
    fetch_mark_after,
    git_cli_enabled,
)
from opal_server.scopes.purge import ScopePurgeCommand
from opal_server.scopes.scope_repository import ScopeNotFoundError, ScopeRepository
from opal_server.scopes.service import ScopesService

# Retry-After hints, in seconds. Two constants rather than one escalating
# value: escalation would need per-client retry state on a stateless endpoint,
# and the expected wait genuinely differs between "a sync will re-create this
# on its next tick" and "a clone is running right now".
_RETRY_AFTER_CLONE_UNAVAILABLE = "5"
_RETRY_AFTER_CLONE_IN_PROGRESS = "30"

# How often the clone wait re-checks the clone. A module constant rather than a
# second config key: the operator-visible quantity is the total hold
# (SCOPES_POLICY_CLONE_WAIT_SECONDS), while every SCOPES_* key is permanent
# public surface — config_docs_drift_test pins each one verbatim into the
# published reference. One poll is a cheap disk read (open the repo, look up
# a ref, read one ref directory), so a second between polls costs at most one
# such read per waiting request per second and still returns within a second
# of the clone landing.
# The published description says "once a second"; a test couples the two.
_CLONE_WAIT_POLL_SECONDS = 1.0

# Ceiling on the configured hold. Above the load balancer's 60s idle timeout a
# hold stops being a hold and becomes a 504 — the exact failure the wait exists
# to prevent — so an over-large value is clamped rather than honoured.
_CLONE_WAIT_MAX_SECONDS = 55.0

# Requests this process is currently holding in the wait. A plain int, no lock:
# it is read and written only from the event loop thread, between awaits, so
# the increment and the cap check cannot interleave with another request's.
_clone_wait_inflight = 0

# The clamp warning latches: on a misconfigured fleet it would otherwise be one
# identical line per request.
_clone_wait_clamp_logged = False

# When this worker last asked every server for a sync of what a bundle request
# found missing (its _claim_key -> loop time): a scope's branch, or a clone. At
# most once per SCOPES_POLICY_BRANCH_REFRESH_INTERVAL, whose description states
# what a branch that really does not exist costs. Event-loop only, like the
# in-flight count, and bounded: the oldest entries go first. One that goes
# early allows an extra request, and releases the requests held for it with
# their 409 at their next poll, as a failed publish does; that takes this many
# scopes missing their branch within one hold.
_branch_refresh_requested: "OrderedDict[Tuple[str, ...], float]" = OrderedDict()
_BRANCH_REFRESH_TRACKED_MAX = 10_000

# Sync requests being published, some after the request that made them stopped
# waiting (its hold ran out, or it was cancelled). Referenced here until they
# end: the event loop keeps only weak references to tasks.
_branch_refresh_publishes: "Set[asyncio.Future[None]]" = set()
# Publishes can outlive their requests; a stuck broadcast backend must not pile
# one up per scope per interval for the life of the worker.
_BRANCH_REFRESH_PUBLISHES_MAX = 1_000
# Claims whose publish failed after a newer claim replaced them (key, claim):
# when that newer publish fails too, they are not put back.
_branch_refresh_failed_claims: "OrderedDict[Tuple[Tuple[str, ...], float], None]" = (
    OrderedDict()
)

_CLONE_WAIT_METRIC = "opal_server.scopes.policy_clone_wait"
_BRANCH_REFRESH_METRIC = "opal_server.scopes.policy_branch_refresh"
_CLONE_WAIT_INFLIGHT_METRIC = "opal_server.scopes.policy_clone_wait_inflight"
_CLONE_WAIT_SECONDS_METRIC = "opal_server.scopes.policy_clone_wait_seconds"
_FRESH_FETCH_METRIC = "opal_server.scopes.policy_fresh_fetch"
_FRESH_FETCH_SECONDS_METRIC = "opal_server.scopes.policy_fresh_fetch_seconds"

# How often a request with no base_hash reads its clone's fetch marks while it
# waits for this server's fetch of the scope's branch (_fresh_fetch_wait): a
# stat of up to three files.
_FRESH_FETCH_POLL_SECONDS = 0.2
# How a fresh-fetch wait can end that the bundle follows without the branch
# wait: one that held its request (the wait stood in for it), and a request
# shed at the in-flight cap, which is served without waiting even when a slot
# is free again by the time its bundle is built.
_FRESH_FETCH_NO_BRANCH_WAIT = frozenset({"fetched", "failed", "timeout", "shed"})
_fresh_fetch_clamp_logged = False
# When this worker last asked every server to fetch a scope's branch for a
# client with no policy (scope id -> loop time), for _fresh_fetch_wait: a
# request while it is younger than the wait rides it. Bounded as the branch
# claims are, apart from them so that neither pushes the other's out.
_fresh_fetch_claims: "OrderedDict[str, float]" = OrderedDict()


def _bounded_clone_wait() -> float:
    """The configured hold, validated and clamped. 0.0 means "do not wait".

    The non-finite trio is what this exists for: `nan`, `inf` and `-inf` all
    parse cleanly, so a process configured with one of them starts normally
    and reaches here. `inf` would silently become the clamped maximum on every
    clone-in-progress request — a 55s hold nobody asked for — and `nan` makes
    every comparison against the deadline False, which the loop is written to
    survive but which is not a budget anyone meant to set.
    """
    global _clone_wait_clamp_logged

    try:
        wait = float(opal_server_config.SCOPES_POLICY_CLONE_WAIT_SECONDS)
    except (TypeError, ValueError):
        # Belt and braces, and NOT the load-bearing half: Confi parses the
        # environment once, when this module is imported, so
        # OPAL_SCOPES_POLICY_CLONE_WAIT_SECONDS=abc already fails the process
        # at startup and never reaches this line. What this covers is a value
        # assigned to the config object at runtime.
        return 0.0
    if not math.isfinite(wait) or wait <= 0:
        return 0.0
    if wait > _CLONE_WAIT_MAX_SECONDS:
        if not _clone_wait_clamp_logged:
            _clone_wait_clamp_logged = True
            logger.warning(
                "SCOPES_POLICY_CLONE_WAIT_SECONDS={configured}s exceeds the "
                "{ceiling}s ceiling and is clamped: a hold longer than the load "
                "balancer's idle timeout is served as a 504, not as a bundle",
                configured=wait,
                ceiling=_CLONE_WAIT_MAX_SECONDS,
            )
        return _CLONE_WAIT_MAX_SECONDS
    return wait


def _bounded_fresh_fetch_wait() -> float:
    """SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS, validated and clamped as the
    clone wait is (_bounded_clone_wait).

    0.0 means "do not wait".
    """
    global _fresh_fetch_clamp_logged

    try:
        wait = float(opal_server_config.SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(wait) or wait <= 0:
        return 0.0
    if wait > _CLONE_WAIT_MAX_SECONDS:
        if not _fresh_fetch_clamp_logged:
            _fresh_fetch_clamp_logged = True
            logger.warning(
                "SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS={configured}s exceeds the "
                "{ceiling}s ceiling and is clamped: a hold longer than the load "
                "balancer's idle timeout is served as a 504, not as a bundle",
                configured=wait,
                ceiling=_CLONE_WAIT_MAX_SECONDS,
            )
        return _CLONE_WAIT_MAX_SECONDS
    return wait


def _publish_clone_wait_inflight() -> None:
    """Publish the held-request count for this process.

    Tagged by pid only. A pod's workers each hold their own count, so an
    untagged series would be last-write-wins across them and a saturated
    worker would be invisible. Deliberately NOT tagged by scope_id or
    source_id: the cap is a per-process resource, and those tags are unbounded
    cardinality.
    """
    metrics.gauge(
        _CLONE_WAIT_INFLIGHT_METRIC,
        _clone_wait_inflight,
        tags={"pid": str(os.getpid())},
    )


def _bounded_branch_refresh_interval() -> float:
    """SCOPES_POLICY_BRANCH_REFRESH_INTERVAL, validated. 0.0 means "off".

    nan, inf and -inf are off too: for an interval, inf would read as
    "ask once, then never again", and nan as nothing at all.
    """
    try:
        interval = float(opal_server_config.SCOPES_POLICY_BRANCH_REFRESH_INTERVAL)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(interval) or interval <= 0:
        return 0.0
    return interval


def _claim_key(
    scope_id: str, fetcher: GitPolicyFetcher, miss: Exception
) -> Tuple[str, ...]:
    """What a miss's sync request is claimed for, so what the interval limits.

    A clone without the scope's branch: the scope, the clone and the
    branch, so a scope that a PUT has moved since its last request asks
    again. No clone, or one just starting: the clone alone, which one
    sync clones for every scope on it. The first element names which.
    """
    if isinstance(miss, BranchHeadNotFoundError):
        return ("branch", scope_id, fetcher.clone_source_id, fetcher.branch)
    return ("clone", fetcher.clone_source_id)


# What a claim's log lines say is missing, by its key's first element.
_MISSING = {
    "branch": "branch in its clone",
    "clone": "clone",
    "commit": "commit its branch names in its clone",
}


def _branch_hold(
    key: Tuple[str, ...], now: float, wait: float
) -> Optional[Tuple[float, bool]]:
    """The claim a miss at ``now`` would hold for (the time the sync ``key``
    names was requested; the hold ends ``wait`` after it), and whether it must
    request the sync itself, without the side effects: None for the immediate
    409 (503 with no clone).

    - No sync requested by this worker within the interval: claim ``now``
      (the caller requests the sync).
    - One requested less than ``wait`` ago: ride that claim, without asking
      again, so concurrent misses ride the same sync.
    - One requested longer ago than that, within the interval: the sync had
      its chance and the branch is still missing, so answer 409 at once.
    """
    interval = _bounded_branch_refresh_interval()
    if interval <= 0:
        return None
    requested = _branch_refresh_requested.get(key)
    if requested is None or now - requested >= interval:
        return now, True
    if now - requested < wait:
        return requested, False
    return None


def _record_branch_refresh(key: Tuple[str, ...], now: float) -> Optional[float]:
    """Claim ``key``'s sync at ``now``; returns the claim it replaced."""
    previous = _branch_refresh_requested.get(key)
    _branch_refresh_requested[key] = now
    _branch_refresh_requested.move_to_end(key)
    while len(_branch_refresh_requested) > _BRANCH_REFRESH_TRACKED_MAX:
        _branch_refresh_requested.popitem(last=False)
    return previous


def _branch_refresh_failed(
    key: Tuple[str, ...],
    claim: float,
    previous: Optional[float],
    exc: BaseException,
    *,
    scope_id: str,
) -> None:
    """A sync request's publish raised: give its claim back, count and log it.

    Only this request's own claim, and the one it replaced is restored,
    unless that one's publish failed too: a newer claim is another
    request's sync, and the requests riding an older one are not this
    publish's to release.
    """
    if _branch_refresh_requested.get(key) == claim:
        if previous is None or (key, previous) in _branch_refresh_failed_claims:
            del _branch_refresh_requested[key]
        else:
            _branch_refresh_requested[key] = previous
    else:
        _branch_refresh_failed_claims[(key, claim)] = None
        while len(_branch_refresh_failed_claims) > _BRANCH_REFRESH_TRACKED_MAX:
            _branch_refresh_failed_claims.popitem(last=False)
    metrics.increment(_BRANCH_REFRESH_METRIC, tags={"outcome": "publish_failed"})
    logger.warning(
        "Scope {scope_id} has no {missing}, and its sync could not be "
        "requested: {exc}",
        scope_id=scope_id,
        missing=_MISSING[key[0]],
        exc=redact_url_in_text(repr(exc)),
    )


def _publish_error(publish: "asyncio.Future[None]") -> Optional[BaseException]:
    """Why an ended publish did not go out, if it did not.

    A publish can end cancelled without its request being cancelled.
    """
    return asyncio.CancelledError() if publish.cancelled() else publish.exception()


def _abandoned_publish_done(
    key: Tuple[str, ...],
    claim: float,
    previous: Optional[float],
    publish: "asyncio.Future[None]",
    *,
    scope_id: str,
) -> None:
    """A publish nobody is waiting for any more ended."""
    error = _publish_error(publish)
    if error is not None:
        _branch_refresh_failed(key, claim, previous, error, scope_id=scope_id)


async def _branch_wait_claim(
    key: Tuple[str, ...],
    request_refresh: Callable[[], Awaitable[None]],
    now: float,
    wait: float,
    deadline: float,
    *,
    scope_id: str,
) -> Optional[float]:
    """The scope's ref, or its clone, is missing from this server's disk:
    request a sync of the scope when this worker has not requested one for
    ``key`` (see _claim_key) within the interval, and return the claim the
    request holds for, ending ``wait`` after it (None: answer at once, without
    a wait).

    The publish is bounded by the request's ``deadline``: a slow broadcast
    backend must not hold the request past its hold. On a timeout the claim
    is kept, since the publish may still go out; if it then raises, the claim
    is given back and the failure reported then. "Timeout" means the publish
    was still running when the hold ended, which includes a clone that landed
    on the hold's last poll.

    A sync that cannot be requested is the same no, and gives this request's
    claim back: holding would wait for a fetch nobody asked for, and keeping
    the claim would answer every miss of the interval at once with no sync
    requested. "Cannot be requested" means a local failure to publish: a
    broadcast backend outage is buffered for replay, not raised, so it counts
    as requested.

    ``policy_branch_refresh`` counts what requests saw, so it does not sum to
    the publishes: ``publish_timeout`` can be followed by ``publish_failed``
    for the same publish, and a request cancelled during a publish that then
    succeeds counts nothing.
    """
    hold = _branch_hold(key, now, wait)
    if hold is None:
        return None
    claim, must_request = hold
    if not must_request:
        return claim  # rides the sync another request asked for
    missing = _MISSING[key[0]]
    if len(_branch_refresh_publishes) >= _BRANCH_REFRESH_PUBLISHES_MAX:
        metrics.increment(_BRANCH_REFRESH_METRIC, tags={"outcome": "publish_backlog"})
        logger.warning(
            "Scope {scope_id} has no {missing}, and its sync was not "
            "requested: {count} earlier requests are still being published",
            scope_id=scope_id,
            missing=missing,
            count=len(_branch_refresh_publishes),
        )
        return None
    previous = _record_branch_refresh(key, now)
    loop = asyncio.get_running_loop()
    publish = asyncio.ensure_future(request_refresh())
    _branch_refresh_publishes.add(publish)
    publish.add_done_callback(_branch_refresh_publishes.discard)
    abandoned = partial(_abandoned_publish_done, key, now, previous, scope_id=scope_id)
    try:
        # asyncio.wait neither cancels the publish nor raises its exception,
        # so a TimeoutError of the publish's own is a failed publish.
        done, _ = await asyncio.wait(
            {publish}, timeout=max(0.0, deadline - loop.time())
        )
    except asyncio.CancelledError:
        publish.add_done_callback(abandoned)
        raise
    if not done:
        publish.add_done_callback(abandoned)
        metrics.increment(_BRANCH_REFRESH_METRIC, tags={"outcome": "publish_timeout"})
        logger.warning(
            "Scope {scope_id} has no {missing}, and its sync request was still "
            "being published when the hold ran out",
            scope_id=scope_id,
            missing=missing,
        )
        return claim
    error = _publish_error(publish)
    if error is not None:
        _branch_refresh_failed(key, now, previous, error, scope_id=scope_id)
        return None
    metrics.increment(_BRANCH_REFRESH_METRIC, tags={"outcome": "requested"})
    logger.info(
        "Scope {scope_id} has no {missing} yet; requested a sync and holding "
        "the request for it",
        scope_id=scope_id,
        missing=missing,
    )
    return claim


async def _request_clone_repair(
    key: Tuple[str, ...],
    request_refresh: Callable[[], Awaitable[None]],
    now: float,
    wait: float,
    *,
    scope_id: str,
) -> None:
    """The clone has the scope's branch ref but not the commit it names: ask
    for a sync of the scope, which finds the commit gone, deletes the clone and
    clones it again. The request itself is answered at once (a 503).

    Asked as the branch wait asks (_branch_wait_claim): once per ``key`` and
    SCOPES_POLICY_BRANCH_REFRESH_INTERVAL on this worker, never with the
    interval or the wait off, and the publish bounded by ``wait``. A publish
    that fails gives its claim back.
    """
    if wait <= 0:
        return
    hold = _branch_hold(key, now, wait)
    if hold is None or not hold[1]:
        return
    if len(_branch_refresh_publishes) >= _BRANCH_REFRESH_PUBLISHES_MAX:
        metrics.increment(_BRANCH_REFRESH_METRIC, tags={"outcome": "publish_backlog"})
        return
    previous = _record_branch_refresh(key, now)
    publish = asyncio.ensure_future(request_refresh())
    _branch_refresh_publishes.add(publish)
    publish.add_done_callback(_branch_refresh_publishes.discard)
    abandoned = partial(_abandoned_publish_done, key, now, previous, scope_id=scope_id)
    try:
        done, _ = await asyncio.wait({publish}, timeout=wait)
    except asyncio.CancelledError:
        publish.add_done_callback(abandoned)
        raise
    if not done:
        publish.add_done_callback(abandoned)
        metrics.increment(_BRANCH_REFRESH_METRIC, tags={"outcome": "publish_timeout"})
        return
    error = _publish_error(publish)
    if error is not None:
        _branch_refresh_failed(key, now, previous, error, scope_id=scope_id)
        return
    metrics.increment(_BRANCH_REFRESH_METRIC, tags={"outcome": "requested"})
    logger.info(
        "Scope {scope_id}'s clone lacks the commit its branch names; requested "
        "a sync, which clones it again",
        scope_id=scope_id,
    )


def _record_fresh_claim(scope_id: str, now: float) -> None:
    _fresh_fetch_claims[scope_id] = now
    _fresh_fetch_claims.move_to_end(scope_id)
    while len(_fresh_fetch_claims) > _BRANCH_REFRESH_TRACKED_MAX:
        _fresh_fetch_claims.popitem(last=False)


def _fresh_publish_failed(scope_id: str, claim: float, exc: BaseException) -> None:
    """A fresh-fetch sync request did not go out: drop its claim, unless a
    newer request replaced it, so that the next request asks again, and the
    requests riding it stop waiting."""
    if _fresh_fetch_claims.get(scope_id) == claim:
        del _fresh_fetch_claims[scope_id]
    logger.warning(
        "Could not ask the servers to fetch the branch of scope {scope_id} for a "
        "client with no policy: {exc}",
        scope_id=scope_id,
        exc=redact_url_in_text(repr(exc)),
    )


def _abandoned_fresh_publish_done(
    scope_id: str, claim: float, publish: "asyncio.Future[None]"
) -> None:
    """A fresh-fetch publish nobody is waiting for any more ended."""
    error = _publish_error(publish)
    if error is not None:
        _fresh_publish_failed(scope_id, claim, error)


def _claim_wall_time(claim: float) -> float:
    """A fresh-fetch claim's loop time as epoch seconds, which fetch marks are
    dated in."""
    return time.time() - (asyncio.get_running_loop().time() - claim)


async def _fresh_fetch_claim(
    scope_id: str,
    request_fetch: Callable[[], Awaitable[None]],
    now: float,
    wait: float,
    *,
    repo_path: pathlib.Path,
    branch: str,
) -> Tuple[float, Optional[str]]:
    """The sync request a fresh-fetch wait holds for: this worker's claim for
    the scope while it is younger than ``wait`` and no fetch of ``branch``
    that started after it has ended (the fetch it asked for is still to
    come, or running: the request takes it, though it may have started
    before this request), else a new one, published now and bounded by the
    wait.

    Returns:
        The claim's loop time, and the outcome that ends the wait at once:
        ``shed`` (too many publishes pending), ``published_failed`` (the
        publish raised; the claim is given back) or ``timeout`` (the
        publish was still running when the wait ended; a later failure
        gives the claim back); None while the wait goes on.
    """
    claim = _fresh_fetch_claims.get(scope_id)
    while claim is not None and now - claim < wait:
        ended = await run_sync(
            fetch_mark_after, repo_path, branch, _claim_wall_time(claim)
        )
        current = _fresh_fetch_claims.get(scope_id)
        if current != claim:
            # Replaced, or given back, while the marks were read.
            claim = current
            continue
        if ended is None:
            return claim, None
        break
    if len(_branch_refresh_publishes) >= _BRANCH_REFRESH_PUBLISHES_MAX:
        return now, "shed"
    _record_fresh_claim(scope_id, now)
    publish = asyncio.ensure_future(request_fetch())
    _branch_refresh_publishes.add(publish)
    publish.add_done_callback(_branch_refresh_publishes.discard)
    abandoned = partial(_abandoned_fresh_publish_done, scope_id, now)
    try:
        done, _ = await asyncio.wait({publish}, timeout=wait)
    except asyncio.CancelledError:
        publish.add_done_callback(abandoned)
        raise
    if not done:
        publish.add_done_callback(abandoned)
        return now, "timeout"
    error = _publish_error(publish)
    if error is not None:
        _fresh_publish_failed(scope_id, now, error)
        return now, "published_failed"
    return now, None


def _count_fresh_fetch(outcome: str, waited: float, scope_id: str) -> None:
    metrics.increment(_FRESH_FETCH_METRIC, tags={"outcome": outcome})
    metrics.gauge(_FRESH_FETCH_SECONDS_METRIC, waited, tags={"outcome": outcome})
    logger.info(
        "Scope {scope_id}: a client with no policy waited {waited:.1f}s for "
        "this server's fetch of the scope's branch ({outcome})",
        scope_id=scope_id,
        waited=waited,
        outcome=outcome,
    )


async def _fresh_fetch_wait(
    fetcher: GitPolicyFetcher,
    repo_path: pathlib.Path,
    scope_id: str,
    request: Optional[Request],
    request_fetch: Callable[[], Awaitable[None]],
) -> Optional[str]:
    """For a bundle request with no base_hash (a client that holds no policy
    yet): ask every server to fetch the scope's branch, and wait up to
    SCOPES_POLICY_FRESH_FETCH_WAIT_SECONDS for this server's fetch.

    With the git command line a fetch asks only for the branches its syncs
    need, so a server that missed a refresh of the scope is not caught up by
    the fetches of other scopes. Only with the git command line, the wait
    above 0, a clone that has landed (the clone wait covers one that has
    not; ``repo_path``) and a branch that can be a ref.

    This server's fetches are read from the clone's fetch marks
    (fetch_mark_after). Only a fetch (a clone, a fetch of every branch)
    that started after the sync request the wait holds for counts: one
    that started before may predate a branch or a commit pushed since.
    One sync request per scope on this worker while it is younger than the
    wait and the fetch it asked for has not ended (_fresh_fetch_claim: the
    requests meanwhile ride it), and the marks are polled every
    _FRESH_FETCH_POLL_SECONDS for a fetch that started after it (the
    leader fetches unless such a fetch stands in). A fetch of the branch
    that failed within the wait before the request answers it at once,
    with nothing published: the source is in its failure backoff, which
    the sync asked for would honour. A request whose claim was given back
    (its publish failed) stops waiting. The request holds a slot of
    SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT for the whole wait, the publish
    included; with none free it does not wait.

    One ``policy_fresh_fetch`` count per request the wait applies to, tagged
    with how it ended, and its duration as ``policy_fresh_fetch_seconds``.

    Returns:
        How the wait ended: ``fetched`` (such a fetch of the branch
        succeeded), ``failed`` (one failed at the remote, or this server's
        sync gave up on fetching), ``timeout``, ``disconnected`` (the
        client hung up), ``cancelled`` (the request was), ``shed`` (no slot
        free, or too many publishes pending) or ``published_failed`` (the
        sync could not be requested); None when the wait does not apply.
    """
    global _clone_wait_inflight

    wait = _bounded_fresh_fetch_wait()
    if wait <= 0 or not git_cli_enabled() or not fetcher.branch_can_be_a_ref():
        return None
    if not await run_sync(clone_landed, repo_path / ".git"):
        return None
    loop = asyncio.get_running_loop()
    started = loop.time()
    recent = await run_sync(
        fetch_mark_after, repo_path, fetcher.branch, time.time() - wait
    )
    if recent is False:
        _count_fresh_fetch("failed", loop.time() - started, scope_id)
        return "failed"
    cap = opal_server_config.SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT
    if 0 < cap <= _clone_wait_inflight:
        _count_fresh_fetch("shed", 0.0, scope_id)
        return "shed"

    # None until the wait has ended one of the ways it counts.
    outcome: Optional[str] = None
    _clone_wait_inflight += 1
    try:
        _publish_clone_wait_inflight()
        claim, ended = await _fresh_fetch_claim(
            scope_id,
            request_fetch,
            started,
            wait,
            repo_path=repo_path,
            branch=fetcher.branch,
        )
        if ended is not None:
            outcome = ended
            return outcome
        since = _claim_wall_time(claim)
        deadline = claim + wait
        while True:
            seen = await run_sync(fetch_mark_after, repo_path, fetcher.branch, since)
            if seen is not None:
                outcome = "fetched" if seen else "failed"
                return outcome
            current = _fresh_fetch_claims.get(scope_id)
            if current is None or current < claim:
                outcome = "published_failed"
                return outcome
            remaining = deadline - loop.time()
            if not (remaining > 0):
                outcome = "timeout"
                return outcome
            await asyncio.sleep(min(_FRESH_FETCH_POLL_SECONDS, remaining))
            if request is not None and await request.is_disconnected():
                outcome = "disconnected"
                return outcome
    except asyncio.CancelledError:
        outcome = "cancelled"
        raise
    finally:
        _clone_wait_inflight -= 1
        _publish_clone_wait_inflight()
        if outcome is not None:
            _count_fresh_fetch(outcome, loop.time() - started, scope_id)


def _make_bundle(fetcher: GitPolicyFetcher, base_hash: Optional[str]) -> PolicyBundle:
    """``fetcher.make_bundle``, with no clone while a git command-line clone of
    it is under way taken for a clone not populated yet.

    That clone is made in a directory beside the clone's path and
    renamed into place once complete, so the path is not there
    meanwhile; a libgit2 clone is made in place, where the empty clone
    gives CloneNotPopulatedError.
    """
    try:
        return fetcher.make_bundle(base_hash)
    except NoSuchPathError as exc:
        # GitPython's NoSuchPathError holds the path it did not find.
        path = pathlib.Path(str(exc))
        if _cli_clone_running(path):
            raise CloneNotPopulatedError(f"A clone into {exc} is under way") from exc
        # The rename can land after make_bundle looked and before the check
        # above. It is atomic and made under the clone's lock, so by now the
        # clone is either in place or not coming.
        if not path.exists():
            raise
    return fetcher.make_bundle(base_hash)


def _cli_clone_running(repo_path: pathlib.Path) -> bool:
    """Whether a git command-line clone of ``repo_path`` is under way: a
    directory a clone is made in sits beside it (clone_under_way), and the
    clone's lock is held, as cli_clone holds it from before it makes that
    directory until after it renames it into place.

    A directory whose lock is free was left by a clone whose process
    died, and nothing will put it in place. Taken for a clone under way
    when the lock cannot be tried (a filesystem that refuses flock).
    """
    if not clone_under_way(repo_path):
        return False
    try:
        fd = take_clone_lock(repo_path)
    except OSError:
        return True
    if fd is None:
        return True
    # Held for no longer than this: a git op that starts meanwhile finds the
    # clone busy and skips it, as for any other holder.
    drop_clone_lock(fd)
    return False


async def _make_bundle_waiting_for_clone(
    fetcher: GitPolicyFetcher,
    base_hash: Optional[str],
    scope_id: str,
    request: Optional[Request] = None,
    request_refresh: Optional[Callable[[], Awaitable[None]]] = None,
    max_wait: float = _CLONE_WAIT_MAX_SECONDS,
) -> PolicyBundle:
    """Build the bundle, holding the request while the clone is populated.

    The immediate 503 this replaces is honest and useless: opal-client
    ignores Retry-After, makes five attempts with random-exponential backoff
    capped at 10s, then stays quiet until the next pub/sub policy message or
    a reconnect. A clone that outlives those attempts leaves that PDP with no
    policy and nothing scheduled to fix it — the update-all published when the
    clone completes names only the scope that was syncing, so siblings sharing
    the clone are never woken.

    Readiness comes from CloneNotPopulatedError, which is derived from disk,
    so this works on the workers that are not running the clone — which is all
    of them but one.

    What is bounded is the WAIT plus at most one more bundle attempt. The
    attempt itself runs on the loop's shared default executor, so time spent
    queued behind other builds is outside the deadline; that queue is what
    SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT bounds, by capping how many requests
    can be released into it at once. Excess requests are shed with the answer
    they would have got before the wait existed.

    The hold takes no lock, touches no cache and occupies no thread between
    polls, so it is cancellation-safe: a client that hangs up mid-wait unwinds
    at the next await with nothing to undo. It is also abandoned as soon as the
    client is seen to have disconnected — nobody is waiting for that bundle,
    and the slot is worth more to a caller that is still listening.

    Returns the bundle, or re-raises CloneNotPopulatedError once the budget is
    spent, so EACH caller's own handler shapes that answer (the primary path
    answers Retry-After 30, the default-scope path 5). Every OTHER exception
    propagates untouched from whichever attempt raised it: a clone can finish
    and still fail to build a bundle (an absent branch is a 409, a gutted
    object store a retryable 503), and the wait must not re-label those.

    One exception to that: a populated clone WITHOUT the scope's branch
    (BranchHeadNotFoundError), or no clone at all (NoSuchPathError, or
    InvalidGitRepositoryError while a clone is just starting), is waited for
    too, when ``request_refresh`` is given (``_branch_wait_claim``). A
    branch pushed after this server's last fetch is the usual cause: every pod
    answers that way right after a scope moves to another repository, until
    its own fetch lands; a pod that has never cloned that repository has no
    clone of it. Such a hold polls one ref (``has_branch_ref``) and builds the
    bundle only once the ref is there. The first miss of a scope's branch (of
    a clone, when there is none: see ``_claim_key``) on this worker within
    SCOPES_POLICY_BRANCH_REFRESH_INTERVAL requests a sync of the scope and is
    held for it; misses while that sync is younger than the wait are held
    too, until the same deadline, without asking again; after that, for the
    rest of the interval, a miss gets the 409 at once. A hold that runs out
    gets the same 409. The in-flight cap is checked
    before any of it, so a request shed there neither requests a sync nor uses
    up the interval, and a request holds its slot while it publishes. A hold
    that runs out without a clone answers the 503 it would have got at once.

    Exactly one `policy_clone_wait` count is emitted per request that reaches
    the wait, tagged with how it ended: served, timeout, shed, disconnected,
    cancelled, error or unrequested (a branch wait whose sync was never
    requested, because its publish failed locally; see
    ``_branch_wait_claim``), and with what it waited for (``for``: clone or
    branch, a missing or just-starting clone included). A first miss whose own
    sync could not be requested (its publish failed, or too many are pending)
    is not a wait: it holds a slot while it publishes, but is counted only in
    ``policy_branch_refresh``.
    The 503 or 409 the caller shapes carries ``waited_seconds`` and
    ``client_disconnected``. ``max_wait`` caps the hold below
    SCOPES_POLICY_CLONE_WAIT_SECONDS: what is left of the ceiling after an
    earlier hold of the same request (_fresh_fetch_wait).
    """
    global _clone_wait_inflight

    waiting_for = "clone"
    try:
        return await run_sync(_make_bundle, fetcher, base_hash)
    except BranchHeadObjectMissingError:
        if request_refresh is not None:
            await _request_clone_repair(
                ("commit", scope_id, fetcher.clone_source_id, fetcher.branch),
                request_refresh,
                asyncio.get_running_loop().time(),
                min(_bounded_clone_wait(), max(0.0, max_wait)),
                scope_id=scope_id,
            )
        raise
    except CloneNotPopulatedError as first_exc:
        wait = min(_bounded_clone_wait(), max(0.0, max_wait))
        if wait <= 0:
            first_exc.waited_seconds = 0.0
            raise
        pending: Exception = first_exc
    except (
        BranchHeadNotFoundError,
        NoSuchPathError,
        InvalidGitRepositoryError,  # a clone just starting; a poll holds for it too
    ) as first_exc:
        wait = min(_bounded_clone_wait(), max(0.0, max_wait))
        if wait <= 0 or request_refresh is None:
            raise
        key = _claim_key(scope_id, fetcher, first_exc)
        # Decided before the cap: a miss that would not wait is not shed from
        # a wait (with the interval off, or after the sync had its chance).
        if _branch_hold(key, asyncio.get_running_loop().time(), wait) is None:
            raise
        pending = first_exc
        waiting_for = "branch"

    # What a shed request is answered.
    status_now = "409" if isinstance(pending, BranchHeadNotFoundError) else "503"
    cap = opal_server_config.SCOPES_POLICY_CLONE_WAIT_MAX_INFLIGHT
    if 0 < cap <= _clone_wait_inflight:
        logger.info(
            "Scope {scope_id} {waiting_for} wait is at its {cap}-request cap; "
            "answering {status} without waiting",
            scope_id=scope_id,
            waiting_for=waiting_for,
            cap=cap,
            status=status_now,
        )
        metrics.increment(
            _CLONE_WAIT_METRIC, tags={"outcome": "shed", "for": waiting_for}
        )
        _note_wait(pending, 0.0)
        raise pending

    loop = asyncio.get_running_loop()
    started = loop.time()
    deadline = started + wait
    # The time of the sync request a branch wait holds for.
    claim = started
    # None: not a wait after all, so not counted as one.
    outcome: Optional[str] = "error"

    # Taken before the publish below, with no await since the cap check: a slow
    # publish holds its request as long as any poll does, so it must count.
    _clone_wait_inflight += 1
    try:
        # Inside the try, not before it: this call ends in a metrics sink, and
        # a sink that raises between the increment and the try would leak the
        # slot for the life of the process — permanently lowering the cap.
        _publish_clone_wait_inflight()
        if waiting_for == "branch":
            assert request_refresh is not None  # checked with the first attempt
            held_for = await _branch_wait_claim(
                key, request_refresh, started, wait, deadline, scope_id=scope_id
            )
            if held_for is None:
                # The immediate 409 or 503, though its publish can have taken time.
                outcome = None
                _note_wait(pending, loop.time() - started)
                raise pending
            claim = held_for
            deadline = min(deadline, claim + wait)
        while True:
            remaining = deadline - loop.time()
            # `not (remaining > 0)` rather than `remaining <= 0`: NaN compares
            # False against BOTH, so the `<=` form does not break on a NaN
            # deadline — it polls forever, holding a capped slot for the life
            # of the process. _bounded_clone_wait already refuses a NaN budget,
            # so this is defence in depth: it makes the loop itself unable to
            # spin if that guard is ever weakened or bypassed.
            if not (remaining > 0):
                outcome = "timeout"
                break
            # Clamped to what is left of the budget, so the last poll cannot
            # overshoot the hold an operator configured.
            await asyncio.sleep(min(_CLONE_WAIT_POLL_SECONDS, remaining))

            if request is not None and await request.is_disconnected():
                outcome = "disconnected"
                logger.info(
                    "Scope {scope_id} {waiting_for} wait abandoned after "
                    "{waited:.1f}s: the client disconnected",
                    scope_id=scope_id,
                    waiting_for=waiting_for,
                    waited=loop.time() - started,
                )
                _note_wait(pending, loop.time() - started, client_disconnected=True)
                raise pending

            bundle: Optional[PolicyBundle] = None
            if waiting_for == "branch":
                # One ref lookup per poll once the clone is known to lack the
                # branch; the bundle is built once the ref is there. A miss of
                # make_bundle costs far more on a clone of a repository with
                # tens of thousands of branches. Until then a poll tries the
                # bundle, which fails at once without a clone and says which
                # answer this hold has come to.
                if not isinstance(pending, BranchHeadNotFoundError) or await run_sync(
                    fetcher.has_branch_ref
                ):
                    try:
                        bundle = await run_sync(_make_bundle, fetcher, base_hash)
                    except (
                        CloneNotPopulatedError,
                        BranchHeadNotFoundError,
                        NoSuchPathError,
                        InvalidGitRepositoryError,
                    ) as exc:
                        pending = exc
                if bundle is None:
                    # After the attempt, so a branch that has just landed is
                    # served. The claim this request holds for was given back
                    # (its publish failed) or evicted: holding on would wait
                    # for a fetch nobody asked for. A newer claim is a sync
                    # requested since, which keeps it held.
                    current = _branch_refresh_requested.get(key)
                    if current is None or current < claim:
                        outcome = "unrequested"
                        _note_wait(pending, loop.time() - started)
                        raise pending
                    continue
            else:
                try:
                    bundle = await run_sync(_make_bundle, fetcher, base_hash)
                except CloneNotPopulatedError as exc:
                    pending = exc
                    continue
                except BranchHeadNotFoundError as exc:
                    pending = exc
                    # The clone landed without the branch: settled once, at
                    # the first miss, like a miss on the first attempt. A miss
                    # that will not be waited for ends the clone wait it was:
                    # counted with `for: clone`, its hold carried to the 409.
                    key = _claim_key(scope_id, fetcher, exc)
                    held_for = (
                        None
                        if request_refresh is None
                        else await _branch_wait_claim(
                            key,
                            request_refresh,
                            loop.time(),
                            wait,
                            deadline,
                            scope_id=scope_id,
                        )
                    )
                    if held_for is None:
                        _note_wait(exc, loop.time() - started)
                        raise
                    waiting_for = "branch"
                    claim = held_for
                    deadline = min(deadline, claim + wait)
                    continue
            outcome = "served"
            logger.info(
                "Scope {scope_id} {waiting_for} became available after "
                "{waited:.1f}s wait",
                scope_id=scope_id,
                waiting_for=waiting_for,
                waited=loop.time() - started,
            )
            return bundle

        # Carried on the exception so each caller can report the hold without
        # this function having to know how the 503 or 409 it falls through to
        # is shaped.
        _note_wait(pending, loop.time() - started)
        raise pending
    except asyncio.CancelledError:
        # A BaseException since 3.8, so no `except Exception` arm would see it.
        # Left uncounted, a fleet whose waits are all being torn down would
        # look exactly like one where nothing is waiting.
        outcome = "cancelled"
        logger.info(
            "Scope {scope_id} {waiting_for} wait cancelled after {waited:.1f}s",
            scope_id=scope_id,
            waiting_for=waiting_for,
            waited=loop.time() - started,
        )
        raise
    except Exception as exc:
        # Only the UNCLASSIFIED failure: `outcome` is already timeout or
        # disconnected when the exception being unwound is `pending`, and
        # those two are logged by whoever shapes the response. This arm is
        # what makes the `error` count readable — a bundle build that failed
        # for its own reasons AFTER the clone appeared.
        if outcome == "error":
            # git errors can embed the remote URL with its auth; bound kwargs
            # reach serialize=True sinks verbatim, so redact before binding.
            logger.info(
                "Scope {scope_id} held {waited:.1f}s waiting for its "
                "{waiting_for} before failing: {exc}",
                scope_id=scope_id,
                waiting_for=waiting_for,
                waited=loop.time() - started,
                exc=redact_url_in_text(repr(exc)),
            )
            _note_wait(exc, loop.time() - started)
        raise
    finally:
        _clone_wait_inflight -= 1
        _publish_clone_wait_inflight()
        if outcome is not None:
            metrics.increment(
                _CLONE_WAIT_METRIC, tags={"outcome": outcome, "for": waiting_for}
            )
        if outcome in ("served", "timeout"):
            metrics.gauge(
                _CLONE_WAIT_SECONDS_METRIC,
                loop.time() - started,
                tags={"outcome": outcome, "for": waiting_for},
            )


def _note_wait(
    exc: Exception, waited_seconds: float, client_disconnected: bool = False
) -> None:
    """Carry the hold on the exception the caller shapes into its 503 or 409.

    Only the two wait exceptions declare the attributes; the route reads
    them off any other with a default.
    """
    exc.waited_seconds = waited_seconds  # type: ignore[attr-defined]
    exc.client_disconnected = client_disconnected  # type: ignore[attr-defined]


def verify_private_key(private_key: str, key_format: EncryptionKeyFormat) -> bool:
    try:
        key = cast_private_key(private_key, key_format=key_format)
        return key is not None
    except Exception as e:
        return False


def verify_private_key_or_throw(scope_in: Scope):
    if isinstance(scope_in.policy.auth, SSHAuthData):
        auth = cast(SSHAuthData, scope_in.policy.auth)
        if not "\n" in auth.private_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "private key is expected to contain newlines!"},
            )

        is_pem_key = verify_private_key(
            auth.private_key, key_format=EncryptionKeyFormat.pem
        )
        is_ssh_key = verify_private_key(
            auth.private_key, key_format=EncryptionKeyFormat.ssh
        )
        if not (is_pem_key or is_ssh_key):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "private key is invalid"},
            )


def verify_branch_or_throw(scope_in: Scope):
    """Refuse a git branch that cannot name a ref: an empty name, or ``x~1``,
    say.

    Such a name is not a branch name git can fetch, so the scope could not
    follow a branch. ``x~1`` still resolves, as a revision expression (the
    parent of ``origin/x``), and a scope stored with one before this check
    is served that commit; a PUT of such a scope, new or an update, gets
    the 422.
    """
    if not isinstance(scope_in.policy, GitPolicyScopeSource):
        return
    fetcher = GitPolicyFetcher(
        pathlib.Path(opal_server_config.BASE_DIR), scope_in.scope_id, scope_in.policy
    )
    if not fetcher.branch_can_be_a_ref():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": f"policy.branch {scope_in.policy.branch!r} "
                "cannot be a git branch name"
            },
        )


def normalize_data_topics_for_scope(
    scope_id: str, config: DataSourceConfig
) -> DataSourceConfig:
    """Return a copy of `config` whose entry topics are namespaced
    `{scope_id}:data:{topic}` — the form a scoped client subscribes to and
    content-filters data entries by (entries with any other topic form are
    silently discarded by the client). Already-namespaced topics pass through
    unchanged, so operator-authored namespaced topics keep working.

    The input config is not modified (the persisted scope keeps the
    operator-authored topic form).
    """
    prefix = f"{scope_id}:data:"
    normalized = config.copy(deep=True)
    for entry in normalized.entries:
        entry.topics = [
            topic if topic.startswith(prefix) else f"{prefix}{topic}"
            for topic in entry.topics
        ]
    return normalized


def init_scope_router(
    scopes: ScopeRepository,
    authenticator: JWTAuthenticator,
    pubsub_endpoint: PubSubEndpoint,
    scopes_service: ScopesService,
):
    router = APIRouter()

    def _allowed_scoped_authenticator(
        claims: JWTClaims = Depends(authenticator), scope_id: str = Path(...)
    ):
        if not authenticator.enabled:
            return

        allowed_scopes = claims.get("allowed_scopes")

        if not allowed_scopes or scope_id not in allowed_scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN)

    @router.put("", status_code=status.HTTP_201_CREATED)
    async def put_scope(
        *,
        force_fetch: bool = Query(
            False,
            description="Whether the policy repo must be fetched from remote",
        ),
        scope_in: Scope,
        claims: JWTClaims = Depends(authenticator),
    ):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to PUT scope: {repr(ex)}")
            raise

        old_source_id = None
        old_clone_path = None
        old_branch = None
        data_config_changed = True
        try:
            old_scope = await scopes.get(scope_in.scope_id)
            data_config_changed = old_scope.data != scope_in.data
            if isinstance(old_scope.policy, GitPolicyScopeSource):
                old_branch = old_scope.policy.branch
                old_source_id = GitPolicyFetcher.source_id(old_scope.policy)
                old_clone_path = str(
                    GitPolicyFetcher.repo_clone_path(
                        pathlib.Path(opal_server_config.BASE_DIR),
                        old_scope.policy,
                    )
                )
        except ScopeNotFoundError:
            pass  # brand-new scope — nothing to repoint away from
        except Exception as e:
            # An unreadable old record must not block the overwrite that
            # fixes it. Its source_id is unknowable anyway, so no purge can be
            # published for it and nothing later will name it — the old clone
            # dir stays on disk until PER-15612's sweep lands.
            logger.warning(
                f"Could not read previous record for scope "
                f"{scope_in.scope_id}, skipping repoint purge: "
                f"{redact_url_in_text(repr(e))}"
            )

        verify_private_key_or_throw(scope_in)
        verify_branch_or_throw(scope_in)

        new_source_id = (
            GitPolicyFetcher.source_id(scope_in.policy)
            if isinstance(scope_in.policy, GitPolicyScopeSource)
            else None
        )
        # The source id names a clone, and with the default single shard every
        # branch of a repository shares one, so it does not see a branch change.
        repointed = old_source_id != new_source_id or (
            isinstance(scope_in.policy, GitPolicyScopeSource)
            and old_branch is not None
            and old_branch != scope_in.policy.branch
        )
        try:
            try:
                await scopes.put(scope_in)
            finally:
                # The repoint purge must stay reachable even when put() raises an
                # ambiguous outcome (committed server-side, error surfaced to the
                # client): a retry would see old_source_id == new_source_id
                # already (the store was updated) and never re-trigger the purge,
                # orphaning the old source permanently. Same channel/handlers as
                # delete — over-publishing self-heals, since the leader
                # sibling-checks and a source still shared by another scope
                # survives.
                if old_source_id is not None and old_source_id != new_source_id:
                    await pubsub_endpoint.publish(
                        [opal_server_config.SCOPES_PURGE_CHANNEL],
                        ScopePurgeCommand(
                            source_id=old_source_id,
                            clone_path=old_clone_path,
                            scope_id=scope_in.scope_id,
                            reason="repoint",
                        ).model_dump(),
                    )

            force_fetch_str = " (force fetch)" if force_fetch else ""
            logger.info(f"Sync scope: {scope_in.scope_id}{force_fetch_str}")

            # All server replicas (leaders) should sync the scope. A repoint (the
            # source or branch changed, or there was no readable previous record)
            # also tells their syncs to notify the scope's clients whatever
            # the clone's scope ref says: a clone of a repository the scope used
            # before still holds the ref it had then (a repoint leaves the old
            # clone on disk), and when the branch head equals it the sync would
            # notify nobody, leaving a client that fetched while the scope pointed
            # elsewhere on that policy. A repoint also forces the fetch: that old
            # clone may not have been fetched since, and an update-all for its
            # stale head would move every client back to an older policy.
            #
            # The flag is lost when put() stored the record and then raised, or a
            # publish raised after it: the retry sees old == new. The request that
            # loses it logs so below. A server without this change never sets it.
            # Either way the sync notifies only when the head differs from the
            # clone's scope ref, as before, so don't repoint scopes while servers
            # are mid-rollout, and a retried repoint is not guaranteed to tell
            # clients whose head did not move.
            await pubsub_endpoint.publish(
                opal_server_config.POLICY_REPO_WEBHOOK_TOPIC,
                {
                    "scope_id": scope_in.scope_id,
                    "force_fetch": force_fetch or repointed,
                    "repointed": repointed,
                },
            )
        except Exception:
            # For a create too: an earlier scope with this id can have left its ref
            # in a clone that outlived its delete, and then the retry's sync finds
            # that ref equal to the branch head and notifies nobody.
            if repointed:
                logger.warning(
                    "Repoint of scope {scope_id} failed before its sync was "
                    "requested. If the record was stored, a retry will not force "
                    "the notify: clients whose head did not move are not told",
                    scope_id=scope_in.scope_id,
                )
            raise

        # Notify already-connected scoped clients about the scope's data source
        # configuration. Clients only fetch /scopes/{scope_id}/data on (re)connect,
        # so without this publish, a client that connected before the scope was
        # created (or before its data config changed) never receives the scope's
        # data sources (issue #779). Entry topics are namespaced to the
        # `{scope_id}:data:{topic}` form the scoped client filters by. Published
        # only when the data config is new or actually changed — mirroring the
        # policy path, which notifies only on new commits.
        if data_config_changed and scope_in.data and scope_in.data.entries:
            await DataUpdatePublisher(
                ServerSideTopicPublisher(pubsub_endpoint)
            ).publish_data_updates(
                DataUpdate(
                    entries=normalize_data_topics_for_scope(
                        scope_in.scope_id, scope_in.data
                    ).entries,
                    reason=f"Scope '{scope_in.scope_id}' data source configuration updated",
                )
            )

        return Response(status_code=status.HTTP_201_CREATED)

    @router.get(
        "",
        response_model=List[Scope],
        # The response is a list, so the exclude must address every item;
        # a bare {"policy": {"auth"}} is silently ignored for a list.
        response_model_exclude={"__all__": {"policy": {"auth"}}},
    )
    async def get_all_scopes(*, claims: JWTClaims = Depends(authenticator)):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to get scopes: {repr(ex)}")
            raise

        return await scopes.all()

    @router.get(
        "/{scope_id}",
        response_model=Scope,
        response_model_exclude={"policy": {"auth"}},
    )
    async def get_scope(*, scope_id: str, claims: JWTClaims = Depends(authenticator)):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to get scope: {repr(ex)}")
            raise

        try:
            scope = await scopes.get(scope_id)
            return scope
        except ScopeNotFoundError:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"No such scope: {scope_id}"
            )

    @router.delete(
        "/{scope_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_scope(
        *, scope_id: str, claims: JWTClaims = Depends(authenticator)
    ):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to delete scope: {repr(ex)}")
            raise

        try:
            # Deletes the record and broadcasts a ScopePurgeCommand; every worker
            # drops its in-memory caches when the leader's confirmation broadcast
            # arrives. The clone dir is removed by THIS worker's best-effort
            # floor, not by the leader — the leader does no disk work (PER-15612).
            await scopes_service.delete_scope(scope_id)
        except ScopeNotFoundError:
            # Deleting a missing scope was always a silent no-op (204); keep it.
            pass

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/{scope_id}/refresh", status_code=status.HTTP_200_OK)
    async def refresh_scope(
        scope_id: str,
        hinted_hash: Optional[str] = Query(
            None,
            description="Commit hash that should exist in the repo. "
            + "If the commit is missing from the local clone, OPAL "
            + "understands it as a hint that the repo should be fetched from remote.",
        ),
        claims: JWTClaims = Depends(authenticator),
    ):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to delete scope: {repr(ex)}")
            raise

        try:
            _ = await scopes.get(scope_id)

            logger.debug(f"Refresh scope: {scope_id}")

            # If the hinted hash is None, we have no way to know whether we should
            # re-fetch the remote, so we force fetch, just in case.
            force_fetch = hinted_hash is None

            # All server replicas (leaders) should sync the scope.
            await pubsub_endpoint.publish(
                opal_server_config.POLICY_REPO_WEBHOOK_TOPIC,
                {
                    "scope_id": scope_id,
                    "force_fetch": force_fetch,
                    "hinted_hash": hinted_hash,
                },
            )

            return Response(status_code=status.HTTP_200_OK)

        except ScopeNotFoundError:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"No such scope: {scope_id}"
            )

    @router.post("/refresh", status_code=status.HTTP_200_OK)
    async def sync_all_scopes(claims: JWTClaims = Depends(authenticator)):
        """Sync all scopes."""
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to refresh all scopes: {repr(ex)}")
            raise

        # All server replicas (leaders) should sync all scopes.
        await pubsub_endpoint.publish(opal_server_config.POLICY_REPO_WEBHOOK_TOPIC)

        return Response(status_code=status.HTTP_200_OK)

    @router.get(
        "/{scope_id}/policy",
        response_model=PolicyBundle,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(_allowed_scoped_authenticator)],
    )
    async def get_scope_policy(
        *,
        request: Request,
        scope_id: str = Path(..., title="Scope ID"),
        base_hash: Optional[str] = Query(
            None,
            description="hash of previous bundle already downloaded, server will return a diff bundle.",
        ),
    ):
        try:
            scope = await scopes.get(scope_id)
        except ScopeNotFoundError:
            logger.warning(
                "Requested scope {scope_id} not found, returning default scope",
                scope_id=scope_id,
            )
            return await _generate_default_scope_bundle(scope_id, request)

        if not isinstance(scope.policy, GitPolicyScopeSource):
            raise HTTPException(
                status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"policy source is not yet implemented: {scope_id}",
            )

        fetcher = GitPolicyFetcher(
            pathlib.Path(opal_server_config.BASE_DIR),
            scope.scope_id,
            cast(GitPolicyScopeSource, scope.policy),
        )

        async def _request_fresh_fetch() -> None:
            # Every leader fetches the scope's branch (batched with its other
            # syncs), honouring the source's backoff, unless a fetch of it
            # that started after this reached it stands in: the requests that
            # reach a server during one fetch share the next. fresh_within
            # (the wait) marks the sync as one a client with no policy asked
            # for.
            await pubsub_endpoint.publish(
                opal_server_config.POLICY_REPO_WEBHOOK_TOPIC,
                {
                    "scope_id": scope_id,
                    "force_fetch": True,
                    "honor_backoff": True,
                    "fresh_within": _bounded_fresh_fetch_wait(),
                },
            )

        async def _request_refresh() -> None:
            # Every leader syncs the scope. Not forced: a sync fetches when the
            # branch is missing from its own clone (_should_fetch), so only the
            # servers that lack it fetch, and the rest do not queue a fetch on
            # the clone's lock in front of every other scope sharing it.
            # It honours the source's failure backoff, as a pass does: a client
            # missing a branch is not someone who has just repaired the source.
            await pubsub_endpoint.publish(
                opal_server_config.POLICY_REPO_WEBHOOK_TOPIC,
                {"scope_id": scope_id, "force_fetch": False, "honor_backoff": True},
            )

        repo_path = GitPolicyFetcher.repo_clone_path(
            pathlib.Path(opal_server_config.BASE_DIR), scope.policy
        )
        fresh: Optional[str] = None
        fresh_started = asyncio.get_running_loop().time()
        if not base_hash and pubsub_endpoint is not None:
            fresh = await _fresh_fetch_wait(
                fetcher,
                repo_path,
                scope_id,
                request,
                _request_fresh_fetch,
            )
        if fresh == "disconnected":
            # Nobody reads this answer.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Policy for scope {scope_id} was not built: the client left",
                headers={"Retry-After": _RETRY_AFTER_CLONE_UNAVAILABLE},
            )
        try:
            return await _make_bundle_waiting_for_clone(
                fetcher,
                base_hash,
                scope_id,
                request,
                # No branch wait for a name no fetch can bring: the request
                # gets its answer at once, and no server is asked to sync it.
                # Nor after a wait for this server's fetch of the branch,
                # which asked for the sync already, nor for a request that
                # wait shed.
                request_refresh=(
                    _request_refresh
                    if pubsub_endpoint is not None
                    and fetcher.branch_can_be_a_ref()
                    and fresh not in _FRESH_FETCH_NO_BRANCH_WAIT
                    else None
                ),
                # Both holds together stay within the clone wait's ceiling.
                max_wait=_CLONE_WAIT_MAX_SECONDS
                - (asyncio.get_running_loop().time() - fresh_started),
            )
        except CloneNotPopulatedError as exc:
            # The clone has no refs/remotes/<remote>/* at all, or is not there
            # while a git command-line clone of it is under way (_make_bundle),
            # so it is being populated right now — _clone() rmtree's the
            # destination and libgit2 clones INTO the final path, so this window
            # is the whole clone. Telling a client its configuration is
            # permanently wrong during the recovery that fixes it is the
            # opposite of the truth.
            #
            # Derived from disk, NOT from the in-flight marker: that marker is a
            # per-process global written only by the leader's sync, while this
            # route is served by any worker, so keying on it answered 409 on
            # every non-leader — N-1 of N workers.
            #
            # Reached once the wait budget, if any, is spent — or straight
            # away when the wait is disabled, shed at the in-flight cap, or the
            # client has already hung up. When a budget was spent, this clone is
            # slower than a client's whole retry budget, so the 503 is a report
            # that waiting did not help rather than a first reflex.
            #
            # Both the line and the event are skipped when the caller has
            # already hung up: this 503 is shaped for a socket nobody is
            # reading, so counting it would inflate the very rate an operator
            # watches to decide whether clients are being served — and the
            # wait has already logged the abandonment once, with the hold.
            if not exc.client_disconnected:
                logger.info(
                    "Scope {scope_id} clone is not populated yet ({exc}), "
                    "returning 503 after waiting {waited:.1f}s",
                    scope_id=scope_id,
                    exc=redact_url_in_text(repr(exc)),
                    waited=exc.waited_seconds,
                )
                metrics.event(
                    "ScopePolicyUnavailable",
                    message=f"Scope {scope_id} policy 503 (clone in progress)",
                    tags={"scope_id": scope_id, "status": "503", "retryable": "true"},
                )
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Policy clone for scope {scope_id} is being created, "
                    "retry shortly"
                ),
                headers={"Retry-After": _RETRY_AFTER_CLONE_IN_PROGRESS},
            )
        except BranchHeadNotFoundError as exc:
            if fresh in ("failed", "timeout") or (
                fresh == "shed"
                and not await run_sync(
                    fetch_mark_after,
                    repo_path,
                    fetcher.branch,
                    time.time() - _bounded_fresh_fetch_wait(),
                )
            ):
                # This server's fetch of the branch did not succeed in time:
                # the remote may well have the branch. A request the wait shed
                # waited for no fetch: the 409 only after a fetch of the branch
                # that succeeded within the wait before it.
                logger.info(
                    "Scope {scope_id} branch is not in this server's clone, and "
                    "no fetch of it succeeded in time ({outcome}): returning 503",
                    scope_id=scope_id,
                    outcome=fresh,
                )
                metrics.event(
                    "ScopePolicyUnavailable",
                    message=f"Scope {scope_id} policy 503 (branch not fetched yet)",
                    tags={"scope_id": scope_id, "status": "503", "retryable": "true"},
                )
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        f"Policy branch for scope {scope_id} is not in this "
                        "server's clone yet, retry shortly"
                    ),
                    headers={"Retry-After": _RETRY_AFTER_CLONE_UNAVAILABLE},
                )
            # Skipped for a caller that hung up during the branch wait, as the
            # 503 arm does: the answer goes nowhere.
            if not exc.client_disconnected:
                logger.error(
                    "Scope {scope_id} bundle unavailable after waiting "
                    "{waited:.1f}s: {exc} (non-retryable)",
                    scope_id=scope_id,
                    waited=exc.waited_seconds,
                    exc=redact_url_in_text(repr(exc)),
                )
                metrics.event(
                    "ScopePolicyUnavailable",
                    message=f"Scope {scope_id} policy 409 (branch unresolved)",
                    tags={
                        "scope_id": scope_id,
                        "status": "409",
                        "retryable": "false",
                    },
                )
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"Policy branch for scope {scope_id} could not be resolved "
                    "(check the configured branch); not retryable"
                ),
            )
        except (
            InvalidGitRepositoryError,
            # A concurrent delete/recovery can rmtree the clone dir before
            # Repo() opens it (NoSuchPathError), or mid-tree-walk (raw
            # OSError). The record exists, so this is transient: recovery or
            # the next sync re-creates the clone. Serving the default
            # scope's bundle here would hand a live tenant another tenant's
            # policy — tell the client to retry instead.
            NoSuchPathError,
            pygit2.GitError,
            ValueError,
            OSError,
        ) as exc:
            # Skipped for a caller that hung up during a hold, as the arms
            # above do: the answer goes nowhere.
            if not getattr(exc, "client_disconnected", False):
                logger.warning(
                    "Scope {scope_id} is live but its clone is unavailable ({exc}), "
                    "returning 503 after waiting {waited:.1f}s",
                    scope_id=scope_id,
                    exc=redact_url_in_text(repr(exc)),
                    waited=getattr(exc, "waited_seconds", 0.0),
                )
                metrics.event(
                    "ScopePolicyUnavailable",
                    message=f"Scope {scope_id} policy 503 (clone unavailable)",
                    tags={"scope_id": scope_id, "status": "503", "retryable": "true"},
                )
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Policy clone for scope {scope_id} is temporarily "
                    "unavailable, retry shortly"
                ),
                headers={"Retry-After": _RETRY_AFTER_CLONE_UNAVAILABLE},
            )

    async def _generate_default_scope_bundle(
        scope_id: str, request: Optional[Request] = None
    ) -> PolicyBundle:
        metrics.event(
            "ScopeNotFound",
            message=f"Scope {scope_id} not found. Serving default scope instead",
            tags={"scope_id": scope_id},
        )

        try:
            scope = await scopes.get("default")
            fetcher = GitPolicyFetcher(
                pathlib.Path(opal_server_config.BASE_DIR),
                scope.scope_id,
                cast(GitPolicyScopeSource, scope.policy),
            )
            # run_sync, like the primary path at the top of this route. Without
            # it a full bundle build — open the repo, walk the commit tree, read
            # and encode every matching file — runs ON THE EVENT LOOP, stalling
            # every other request this worker is serving, including other
            # tenants' bundles and the pub/sub websocket traffic. Reached by any
            # GET for an unknown scope, which a PDP with a stale id re-hits on
            # its normal poll cadence.
            #
            # Waits for the default clone on the same terms as the primary
            # path: this is the branch every PDP holding a stale scope id
            # takes, and the default scope's clone is populated by the same
            # recovery as any other. On expiry the re-raised
            # CloneNotPopulatedError lands in the broad tuple below, so this
            # path keeps ITS contract (Retry-After 5), not the primary path's.
            return await _make_bundle_waiting_for_clone(
                fetcher, None, scope.scope_id, request
            )
        except ScopeNotFoundError:
            # 404, not a bare ScopeNotFoundError. Nothing registers an exception
            # handler for that, so it escaped the route as an unhandled 500 —
            # for the ordinary case of an unknown scope on a deployment that has
            # no "default" scope at all. get_scope and refresh_scope already
            # answer 404 here; this now matches them.
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"No such scope: {scope_id}"
            )
        except CloneNotPopulatedError as exc:
            # Its own arm, ahead of the broad tuple that would otherwise catch
            # it (CloneNotPopulatedError subclasses ValueError), for one
            # reason: only this exception carries the hold, and a 503 that does
            # not say how long the server waited cannot be told apart from one
            # that never waited. Same 503 + Retry-After 5 as the tuple below —
            # this path's contract is unchanged. Silent when the caller has
            # already hung up, like the primary path.
            if not exc.client_disconnected:
                logger.warning(
                    "Default-scope bundle for {scope_id} is temporarily "
                    "unavailable after waiting {waited:.1f}s ({exc}), "
                    "returning 503",
                    scope_id=scope_id,
                    waited=exc.waited_seconds,
                    exc=redact_url_in_text(repr(exc)),
                )
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Policy clone for scope {scope_id} is temporarily "
                    "unavailable, retry shortly"
                ),
                headers={"Retry-After": _RETRY_AFTER_CLONE_UNAVAILABLE},
            )
        except BranchHeadNotFoundError as exc:
            # Ahead of the broad tuple (it subclasses ValueError), for the
            # level: a default scope's wrong branch is not a temporary
            # condition, whatever this path answers. Same 503 as the tuple.
            logger.error(
                "Default-scope bundle for {scope_id} is unavailable: {exc}, "
                "returning 503",
                scope_id=scope_id,
                exc=redact_url_in_text(repr(exc)),
            )
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Policy clone for scope {scope_id} is temporarily "
                    "unavailable, retry shortly"
                ),
                headers={"Retry-After": _RETRY_AFTER_CLONE_UNAVAILABLE},
            )
        except (
            InvalidGitRepositoryError,
            NoSuchPathError,
            pygit2.GitError,
            OSError,
            ValueError,
        ) as exc:
            # A TRANSIENT fault building the default scope's bundle is not
            # "no such scope". These are the same exceptions the primary path
            # answers with 503 forty lines up, on the same reasoning: the clone
            # is being recovered and will be back. Folding them into the 404
            # told a client to stop asking about a condition that self-heals in
            # seconds — and §6 explicitly tells third-party consumers to act on
            # these codes, so it was wrong in the unsafe direction.
            logger.warning(
                "Default-scope bundle for {scope_id} is temporarily unavailable "
                "({exc}), returning 503",
                scope_id=scope_id,
                exc=redact_url_in_text(repr(exc)),
            )
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Policy clone for scope {scope_id} is temporarily "
                    "unavailable, retry shortly"
                ),
                headers={"Retry-After": _RETRY_AFTER_CLONE_UNAVAILABLE},
            )

    @router.get(
        "/{scope_id}/data",
        response_model=DataSourceConfig,
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(_allowed_scoped_authenticator)],
    )
    async def get_scope_data_config(
        *,
        scope_id: str = Path(..., title="Scope ID"),
        authorization: Optional[str] = Header(None),
    ):
        logger.info(
            "Serving source configuration for scope {scope_id}", scope_id=scope_id
        )
        try:
            scope = await scopes.get(scope_id)
            # Serve entry topics in the namespaced `{scope_id}:data:{topic}` form
            # the scoped client filters by — entries authored with bare/default
            # topics (e.g. the schema default `policy_data`) would otherwise be
            # silently discarded by the client (the #779 symptom via the happy
            # path). The persisted scope keeps the authored form.
            return normalize_data_topics_for_scope(scope_id, scope.data)
        except ScopeNotFoundError as ex:
            logger.warning(
                "Requested scope {scope_id} not found, serving an empty data-source config",
                scope_id=scope_id,
            )
            try:
                config: ServerDataSourceConfig = opal_server_config.DATA_CONFIG_SOURCES

                if config.external_source_url:
                    url = str(config.external_source_url)
                    token = get_token_from_header(authorization)
                    redirect_url = set_url_query_param(url, "token", token)
                    return RedirectResponse(url=redirect_url)
                else:
                    # A scope that is not (yet) in the repository has no
                    # scope-specific data sources to serve. Returning the
                    # server-global OPAL_DATA_CONFIG_SOURCES here leaks the
                    # default `policy_data` topic, which a scoped agent
                    # (subscribed to `<scope_id>:data:<topic>`) discards as
                    # topic-mismatched -- so it loads no data at all (issue #779).
                    # Serve an empty, scope-shaped config instead of the wrong default.
                    return DataSourceConfig(entries=[])
            except ScopeNotFoundError:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(ex))

    @router.post("/{scope_id}/data/update")
    async def publish_data_update_event(
        update: DataUpdate,
        claims: JWTClaims = Depends(authenticator),
        scope_id: str = Path(..., description="Scope ID"),
    ):
        try:
            require_peer_type(authenticator, claims, PeerType.datasource)

            restrict_optional_topics_to_publish(authenticator, claims, update)

            for entry in update.entries:
                entry.topics = [f"{scope_id}:data:{topic}" for topic in entry.topics]

            await DataUpdatePublisher(
                ServerSideTopicPublisher(pubsub_endpoint)
            ).publish_data_updates(update)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to publish update: {repr(ex)}")
            raise

    return router
