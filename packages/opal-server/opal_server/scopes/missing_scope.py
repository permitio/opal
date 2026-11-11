"""What a request for a scope that is not stored reports.

GET /scopes/{scope_id}/policy and GET /scopes/{scope_id}/data answer such a
request as SCOPES_MISSING_SCOPE says. Either way it counts
opal_server.scopes.missing_scope and, with SCOPES_MISSING_SCOPE_WEBHOOK_URL
set, the worker POSTs the scope's id there, so that whatever writes the
scopes can put the record back: once per scope per window, in a task of its
own, so the request never waits for the webhook nor fails with it.
"""

import asyncio
import datetime
import time
from collections import OrderedDict
from enum import Enum
from functools import partial
from typing import Dict, List, Optional, Set
from urllib.parse import urlsplit

import aiohttp
from opal_common.http_utils import redact_sensitive_text
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_server.config import opal_server_config

MISSING_SCOPE_METRIC = "opal_server.scopes.missing_scope"
WEBHOOK_METRIC = "opal_server.scopes.missing_scope_webhook"

# One POST per scope per this many seconds per worker. The published
# descriptions say "5 minutes", "a 5-second timeout" and "100 at a time".
_WEBHOOK_WINDOW_SECONDS = 300.0
_WEBHOOK_TIMEOUT_SECONDS = 5.0
# POSTs under way at once per worker: a receiver that is slow must not
# collect one task per missing scope.
_WEBHOOK_MAX_INFLIGHT = 100
# Scopes remembered as posted within the window, the oldest forgotten first:
# one forgotten early can be posted again inside its window.
_WEBHOOK_TRACKED_MAX = 10_000


class MissingScopeMode(str, Enum):
    """What a missing scope's policy and data requests answer."""

    default = "default"
    not_found = "not_found"


def _now() -> float:
    return time.monotonic()


def missing_scope_mode() -> MissingScopeMode:
    """SCOPES_MISSING_SCOPE, which validate_missing_scope_settings checked at
    start."""
    return MissingScopeMode(opal_server_config.SCOPES_MISSING_SCOPE)


def validate_missing_scope_settings() -> None:
    """Stop a scopes server whose missing-scope settings cannot work.

    Neither the token nor the URL's credentials go into an error.

    Raises:
        ValueError: SCOPES_MISSING_SCOPE is neither default nor not_found;
            the webhook URL is not an http:// or https:// URL with a host,
            or carries a password while the token is set; the token is set
            without the URL.
    """
    if not opal_server_config.SCOPES:
        return
    modes = {mode.value for mode in MissingScopeMode}
    if opal_server_config.SCOPES_MISSING_SCOPE not in modes:
        raise ValueError(
            f"OPAL_SCOPES_MISSING_SCOPE is {opal_server_config.SCOPES_MISSING_SCOPE!r}: "
            "set it to default or not_found"
        )
    url = opal_server_config.SCOPES_MISSING_SCOPE_WEBHOOK_URL
    token = opal_server_config.SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN
    if not url:
        if token:
            raise ValueError(
                "OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN is set without "
                "OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_URL: set the URL, or unset the token"
            )
        return
    try:
        parts = urlsplit(url)
        # .port raises on a port that is not a number in range.
        scheme, host, password, _ = (
            parts.scheme.lower(),
            parts.hostname,
            parts.password,
            parts.port,
        )
    except ValueError:
        scheme, host, password = "", None, None
    if scheme not in ("http", "https") or not host:
        raise ValueError(
            f"OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_URL ({_shown(url)}) is not an "
            "http:// or https:// URL with a host"
        )
    if password and token:
        raise ValueError(
            f"OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_URL ({_shown(url)}) carries a "
            "password and OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN is set: a POST "
            "carries one of them, so drop one"
        )


def _shown(url: str) -> str:
    """What is logged of the webhook URL: its scheme, host and port.

    A webhook's path or query often holds its secret, and its user info a
    password.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return "a URL that does not parse"
    if not parts.scheme or not host:
        return "a URL with no scheme or no host"
    if ":" in host:
        host = f"[{host}]"
    return f"{parts.scheme}://{host}" + (f":{port}" if port is not None else "")


def _after_the_host(url: str) -> List[str]:
    """The parts of ``url`` after its host that are never logged: its path with
    the query and fragment, and its path alone."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return []
    tail = url.split(parts.netloc, 1)[-1] if parts.netloc else ""
    return [part for part in (tail, parts.path) if len(part) > 1]


class MissingScopeReporter:
    """Counts each request for a scope that is not stored and posts the scope
    to the webhook, for one worker.

    Lives on the event loop: ``report`` runs between awaits, so its
    bookkeeping needs no lock.
    """

    def __init__(self) -> None:
        # scope id -> when it was posted, oldest first.
        self._posted: "OrderedDict[str, float]" = OrderedDict()
        # The POSTs under way. Referenced here until they end: the event
        # loop keeps only weak references to tasks.
        self._posts: "Set[asyncio.Task[None]]" = set()

    def report(self, scope_id: str, route: str) -> None:
        """Count a request of ``route`` (policy or data) for ``scope_id``,
        which is not stored, and post it unless this worker posted that scope
        within the window.

        Returns at once: the POST runs in a task of its own.
        """
        # Not tagged with the scope id: a series per scope would be unbounded
        # (a store loss makes one per stored scope, and with authentication off
        # every invented id makes one). The WARNING and the POST name it.
        metrics.increment(MISSING_SCOPE_METRIC, tags={"route": route})
        url = opal_server_config.SCOPES_MISSING_SCOPE_WEBHOOK_URL
        if not url:
            return
        now = _now()
        self._forget_posted_before(now - _WEBHOOK_WINDOW_SECONDS)
        if scope_id in self._posted:
            return
        if len(self._posts) >= _WEBHOOK_MAX_INFLIGHT:
            # Not remembered as posted: a later request for it posts it.
            metrics.increment(WEBHOOK_METRIC, tags={"outcome": "shed"})
            return
        self._posted[scope_id] = now
        while len(self._posted) > _WEBHOOK_TRACKED_MAX:
            self._posted.popitem(last=False)
        body = {
            "scope_id": scope_id,
            "route": route,
            "seen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="milliseconds"
            ),
        }
        token = opal_server_config.SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN
        post = asyncio.get_running_loop().create_task(_post(url, token, body))
        self._posts.add(post)
        post.add_done_callback(partial(self._post_done, url, token, scope_id))

    def _forget_posted_before(self, cutoff: float) -> None:
        while self._posted:
            scope_id, posted_at = next(iter(self._posted.items()))
            if posted_at > cutoff:
                return
            del self._posted[scope_id]

    def _post_done(
        self, url: str, token: Optional[str], scope_id: str, post: "asyncio.Task[None]"
    ) -> None:
        self._posts.discard(post)
        if post.cancelled():
            return
        error = post.exception()
        if error is not None:
            # _post handles every failure of the POST itself; this is a bug.
            metrics.increment(WEBHOOK_METRIC, tags={"outcome": "error"})
            logger.error(
                "Missing-scope webhook could not report scope {scope_id} to {url}: "
                "{error}",
                scope_id=scope_id,
                url=_shown(url),
                error=_describe(error, url, token),
            )


def _describe(error: BaseException, url: str, token: Optional[str]) -> str:
    """``error`` as text with no credential: of the URL only what ``_shown``
    shows, no token, no Authorization value."""
    text = f"{type(error).__name__}: {error}".replace(url, _shown(url))
    for part in _after_the_host(url):
        text = text.replace(part, "/...")
    text = redact_sensitive_text(text)
    if token:
        text = text.replace(token, "***")
    return text


async def _post(url: str, token: Optional[str], body: Dict[str, str]) -> None:
    """POST ``body`` to the webhook once, and count and log how it went."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    shown = _shown(url)
    scope_id = body["scope_id"]
    timeout = aiohttp.ClientTimeout(total=_WEBHOOK_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=body, headers=headers) as response:
                status = response.status
    except TimeoutError:
        outcome, detail = "timeout", f"no answer in {_WEBHOOK_TIMEOUT_SECONDS:g}s"
    except (aiohttp.ClientError, OSError) as error:
        outcome, detail = "failed", _describe(error, url, token)
    else:
        if 200 <= status < 300:
            metrics.increment(WEBHOOK_METRIC, tags={"outcome": "sent"})
            logger.debug(
                "Reported missing scope {scope_id} to {url}",
                scope_id=scope_id,
                url=shown,
            )
            return
        outcome, detail = "rejected", f"it answered {status}"
    metrics.increment(WEBHOOK_METRIC, tags={"outcome": outcome})
    logger.warning(
        "Missing-scope webhook could not report scope {scope_id} to {url}: {detail}",
        scope_id=scope_id,
        url=shown,
        detail=detail,
    )
