import asyncio
import math
import os
import pathlib
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
from opal_common.topics.publisher import (
    ScopedServerSideTopicPublisher,
    ServerSideTopicPublisher,
)
from opal_common.urls import set_url_query_param
from opal_server.config import opal_server_config
from opal_server.data.data_update_publisher import DataUpdatePublisher
from opal_server.git_fetcher import (
    BranchHeadNotFoundError,
    CloneNotPopulatedError,
    GitPolicyFetcher,
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

# When this worker last asked every server to sync a scope whose clone lacked
# its branch (scope id -> loop time): at most once per
# SCOPES_POLICY_BRANCH_REFRESH_INTERVAL, whose description states what a branch
# that really does not exist costs. Event-loop only, like the in-flight count,
# and bounded: the oldest entries go first. One that goes early allows an extra
# request, and releases the requests held for it with their 409 at their next
# poll, as a failed publish does; that takes this many scopes missing their
# branch within one hold.
_branch_refresh_requested: "OrderedDict[str, float]" = OrderedDict()
_BRANCH_REFRESH_TRACKED_MAX = 10_000

# Sync requests being published, some after the request that made them stopped
# waiting (its hold ran out, or it was cancelled). Referenced here until they
# end: the event loop keeps only weak references to tasks.
_branch_refresh_publishes: "Set[asyncio.Future[None]]" = set()

_CLONE_WAIT_METRIC = "opal_server.scopes.policy_clone_wait"
_BRANCH_REFRESH_METRIC = "opal_server.scopes.policy_branch_refresh"
_CLONE_WAIT_INFLIGHT_METRIC = "opal_server.scopes.policy_clone_wait_inflight"
_CLONE_WAIT_SECONDS_METRIC = "opal_server.scopes.policy_clone_wait_seconds"


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


def _branch_hold(
    scope_id: str, now: float, wait: float
) -> Optional[Tuple[float, bool]]:
    """The claim a miss of ``scope_id`` at ``now`` would hold for (the time its
    sync was requested; the hold ends ``wait`` after it), and whether it must
    request the sync itself, without the side effects: None for the immediate
    409.

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
    requested = _branch_refresh_requested.get(scope_id)
    if requested is None or now - requested >= interval:
        return now, True
    if now - requested < wait:
        return requested, False
    return None


def _record_branch_refresh(scope_id: str, now: float) -> Optional[float]:
    """Claim ``scope_id``'s sync at ``now``; returns the claim it replaced."""
    previous = _branch_refresh_requested.get(scope_id)
    _branch_refresh_requested[scope_id] = now
    _branch_refresh_requested.move_to_end(scope_id)
    while len(_branch_refresh_requested) > _BRANCH_REFRESH_TRACKED_MAX:
        _branch_refresh_requested.popitem(last=False)
    return previous


def _branch_refresh_failed(
    scope_id: str, claim: float, previous: Optional[float], exc: BaseException
) -> None:
    """A sync request's publish raised: give its claim back, count and log it.

    Only this request's own claim, and the one it replaced is restored:
    a newer claim is another request's sync, and the requests riding an
    older one are not this publish's to release.
    """
    if _branch_refresh_requested.get(scope_id) == claim:
        if previous is None:
            del _branch_refresh_requested[scope_id]
        else:
            _branch_refresh_requested[scope_id] = previous
    metrics.increment(_BRANCH_REFRESH_METRIC, tags={"outcome": "publish_failed"})
    logger.warning(
        "Scope {scope_id} has no branch in its clone, and its sync could "
        "not be requested: {exc}",
        scope_id=scope_id,
        exc=redact_url_in_text(repr(exc)),
    )


def _abandoned_publish_done(
    scope_id: str,
    claim: float,
    previous: Optional[float],
    publish: "asyncio.Future[None]",
) -> None:
    """A publish nobody is waiting for any more ended."""
    if not publish.cancelled() and publish.exception() is not None:
        _branch_refresh_failed(scope_id, claim, previous, publish.exception())


async def _branch_wait_claim(
    scope_id: str,
    request_refresh: Callable[[], Awaitable[None]],
    now: float,
    wait: float,
    deadline: float,
) -> Optional[float]:
    """The scope's ref is missing from this server's disk: request a sync of
    the scope when this worker has not within the interval, and return the
    claim the request holds for, ending ``wait`` after it (None: answer at
    once, without a wait).

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
    """
    hold = _branch_hold(scope_id, now, wait)
    if hold is None:
        return None
    claim, must_request = hold
    if not must_request:
        return claim  # rides the sync another request asked for
    previous = _record_branch_refresh(scope_id, now)
    loop = asyncio.get_running_loop()
    publish = asyncio.ensure_future(request_refresh())
    _branch_refresh_publishes.add(publish)
    publish.add_done_callback(_branch_refresh_publishes.discard)
    abandoned = partial(_abandoned_publish_done, scope_id, now, previous)
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
            "Scope {scope_id} has no branch in its clone, and its sync request "
            "was still being published when the hold ran out",
            scope_id=scope_id,
        )
        return claim
    try:
        publish.result()
    except Exception as exc:
        _branch_refresh_failed(scope_id, now, previous, exc)
        return None
    metrics.increment(_BRANCH_REFRESH_METRIC, tags={"outcome": "requested"})
    logger.info(
        "Scope {scope_id} has no branch in its clone yet; requested a sync and "
        "holding the request for it",
        scope_id=scope_id,
    )
    return claim


async def _make_bundle_waiting_for_clone(
    fetcher: GitPolicyFetcher,
    base_hash: Optional[str],
    scope_id: str,
    request: Optional[Request] = None,
    request_refresh: Optional[Callable[[], Awaitable[None]]] = None,
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
    (BranchHeadNotFoundError), or no clone at all (NoSuchPathError), is waited
    for too, when ``request_refresh`` is given (``_branch_wait_claim``). A
    branch pushed after this server's last fetch is the usual cause: every pod
    answers that way right after a scope moves to another repository, until
    its own fetch lands; a pod that has never cloned that repository has no
    clone of it. Such a hold polls one ref (``has_branch_ref``) and builds the
    bundle only once the ref is there. The first miss of
    a scope on this worker within SCOPES_POLICY_BRANCH_REFRESH_INTERVAL
    requests a sync of the scope and is held for it; misses while that sync is
    younger than the wait are held too, until the same deadline, without asking
    again; after that, for the rest of the interval, a miss gets the 409 at
    once. A hold that runs out gets the same 409. The in-flight cap is checked
    before any of it, so a request shed there neither requests a sync nor uses
    up the interval. A request that has just requested the sync is checked
    again; if it is shed then, the sync it requested stands for the interval
    and later misses ride it. A hold that runs out without a clone answers the
    503 it would have got at once.

    Exactly one `policy_clone_wait` count is emitted per request that reaches
    the wait, tagged with how it ended: served, timeout, shed, disconnected,
    cancelled, error or unrequested (a branch wait whose sync was never
    requested, because its publish failed locally; see
    ``_branch_wait_claim``), and with what it waited for (``for``: clone or
    branch, a missing clone included).
    The 503 or 409 the caller shapes carries ``waited_seconds`` and
    ``client_disconnected``.
    """
    global _clone_wait_inflight

    waiting_for = "clone"
    try:
        return await run_sync(fetcher.make_bundle, base_hash)
    except CloneNotPopulatedError as first_exc:
        wait = _bounded_clone_wait()
        if wait <= 0:
            first_exc.waited_seconds = 0.0
            raise
        pending: Exception = first_exc
    except (BranchHeadNotFoundError, NoSuchPathError) as first_exc:
        wait = _bounded_clone_wait()
        if wait <= 0 or request_refresh is None:
            raise
        # Decided before the cap: a miss that would not wait is not shed from
        # a wait (with the interval off, or after the sync had its chance).
        if _branch_hold(scope_id, asyncio.get_running_loop().time(), wait) is None:
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
    if waiting_for == "branch":
        assert request_refresh is not None  # checked with the first attempt
        held_for = await _branch_wait_claim(
            scope_id, request_refresh, started, wait, deadline
        )
        if held_for is None:
            raise pending  # the immediate 409 or 503: not a wait
        claim = held_for
        deadline = min(deadline, claim + wait)
        # Again: a request that published yielded in the publish, and other
        # first misses may have taken slots meanwhile. The sync is requested
        # by now, so later misses can still ride it.
        if 0 < cap <= _clone_wait_inflight:
            logger.info(
                "Scope {scope_id} branch wait is at its {cap}-request cap; "
                "answering {status} without waiting",
                scope_id=scope_id,
                cap=cap,
                status=status_now,
            )
            metrics.increment(
                _CLONE_WAIT_METRIC, tags={"outcome": "shed", "for": waiting_for}
            )
            _note_wait(pending, 0.0)
            raise pending
    outcome = "error"

    _clone_wait_inflight += 1
    try:
        # Inside the try, not before it: this call ends in a metrics sink, and
        # a sink that raises between the increment and the try would leak the
        # slot for the life of the process — permanently lowering the cap.
        _publish_clone_wait_inflight()
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
                # One ref lookup per poll; the bundle is built once the ref is
                # there. A miss of make_bundle costs far more on a clone of a
                # repository with tens of thousands of branches.
                if await run_sync(fetcher.has_branch_ref):
                    try:
                        bundle = await run_sync(fetcher.make_bundle, base_hash)
                    except (
                        CloneNotPopulatedError,
                        BranchHeadNotFoundError,
                        NoSuchPathError,
                    ) as exc:
                        pending = exc
                if bundle is None:
                    # After the attempt, so a branch that has just landed is
                    # served. The claim this request holds for was given back
                    # (its publish failed) or evicted: holding on would wait
                    # for a fetch nobody asked for. A newer claim is a sync
                    # requested since, which keeps it held.
                    current = _branch_refresh_requested.get(scope_id)
                    if current is None or current < claim:
                        outcome = "unrequested"
                        _note_wait(pending, loop.time() - started)
                        raise pending
                    continue
            else:
                try:
                    bundle = await run_sync(fetcher.make_bundle, base_hash)
                except CloneNotPopulatedError as exc:
                    pending = exc
                    continue
                except BranchHeadNotFoundError as exc:
                    pending = exc
                    # The clone landed without the branch: settled once, at
                    # the first miss, like a miss on the first attempt. A miss
                    # that will not be waited for ends the clone wait it was:
                    # counted with `for: clone`, its hold carried to the 409.
                    held_for = (
                        None
                        if request_refresh is None
                        else await _branch_wait_claim(
                            scope_id, request_refresh, loop.time(), wait, deadline
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
        raise
    finally:
        _clone_wait_inflight -= 1
        _publish_clone_wait_inflight()
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

    Both wait exceptions declare the two attributes; anything else
    passes through untouched.
    """
    if isinstance(exc, (CloneNotPopulatedError, BranchHeadNotFoundError)):
        exc.waited_seconds = waited_seconds
        exc.client_disconnected = client_disconnected


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
        try:
            old_scope = await scopes.get(scope_in.scope_id)
            if isinstance(old_scope.policy, GitPolicyScopeSource):
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

        new_source_id = (
            GitPolicyFetcher.source_id(scope_in.policy)
            if isinstance(scope_in.policy, GitPolicyScopeSource)
            else None
        )
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
        # source changed, or there was no readable previous record to compare
        # with) also tells their syncs to notify the scope's clients whatever
        # the clone's scope ref says: a clone of a repository the scope used
        # before still holds the ref it had then (a repoint leaves the old
        # clone on disk), and when the branch head equals it the sync would
        # notify nobody, leaving a client that fetched while the scope pointed
        # elsewhere on that policy. A repoint also forces the fetch: that old
        # clone may not have been fetched since, and an update-all for its
        # stale head would move every client back to an older policy.
        #
        # Unlike the purge above, the flag is not published from the finally,
        # so it is lost when put() stored the record and then raised: the
        # retry sees old == new. A server without this change never sets it.
        # Either way the sync notifies only when the head differs from the
        # clone's scope ref, as before, so don't repoint scopes while servers
        # are mid-rollout, and a retried repoint is not guaranteed to tell
        # clients whose head did not move.
        repointed = old_source_id != new_source_id
        await pubsub_endpoint.publish(
            opal_server_config.POLICY_REPO_WEBHOOK_TOPIC,
            {
                "scope_id": scope_in.scope_id,
                "force_fetch": force_fetch or repointed,
                "repointed": repointed,
            },
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

        try:
            return await _make_bundle_waiting_for_clone(
                fetcher,
                base_hash,
                scope_id,
                request,
                request_refresh=(
                    _request_refresh if pubsub_endpoint is not None else None
                ),
            )
        except CloneNotPopulatedError as exc:
            # The clone has no refs/remotes/<remote>/* at all, so it is being
            # populated right now — _clone() rmtree's the destination and clones
            # INTO the final path, so this window is the whole clone. Telling a
            # client its configuration is permanently wrong during the recovery
            # that fixes it is the opposite of the truth.
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
            logger.warning(
                "Scope {scope_id} is live but its clone is unavailable ({exc}), "
                "returning 503",
                scope_id=scope_id,
                exc=redact_url_in_text(repr(exc)),
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
            return scope.data
        except ScopeNotFoundError as ex:
            logger.warning(
                "Requested scope {scope_id} not found, returning OPAL_DATA_CONFIG_SOURCES",
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
                    return config.config
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
                entry.topics = [f"data:{topic}" for topic in entry.topics]

            await DataUpdatePublisher(
                ScopedServerSideTopicPublisher(pubsub_endpoint, scope_id)
            ).publish_data_updates(update)
        except Unauthorized as ex:
            logger.error(f"Unauthorized to publish update: {repr(ex)}")
            raise

    return router
