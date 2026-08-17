import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

import aiohttp
from fastapi import HTTPException, status
from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_common.schemas.policy import PolicyBundle
from opal_common.security.sslcontext import get_custom_ssl_context
from opal_common.utils import (
    get_authorization_header,
    throw_if_bad_status_code,
    tuple_to_dict,
)
from pydantic import ValidationError
from tenacity import retry, retry_if_not_exception_type, stop, wait
from tenacity.wait import wait_base

# Statuses the OPAL server uses to say "this will work later, come back":
#   503 - the scope's repo clone is in progress, or its clone vanished/is corrupt
#   429 - the server (or something in front of it) is shedding load
# Both may carry a `Retry-After` header telling us how long to wait.
RETRYABLE_BUNDLE_STATUSES = frozenset(
    {status.HTTP_503_SERVICE_UNAVAILABLE, status.HTTP_429_TOO_MANY_REQUESTS}
)

# Statuses that will NOT fix themselves by asking again:
#   409 - the scope's branch could not be resolved in the policy repo
# (404 is handled separately, so that it keeps raising an HTTPException.)
NON_RETRYABLE_BUNDLE_STATUSES = frozenset({status.HTTP_409_CONFLICT})


class BundleFetchError(Exception):
    """A bundle request that the server answered with a status we classified.

    Carries the status code and the server's `detail` so callers (and
    logs) can tell a "come back later" apart from a "this will never
    work".
    """

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        # Deliberately NOT `super().__init__(...)`: BundlePathNotFoundError also
        # inherits fastapi's HTTPException, and a cooperative super() would hand
        # this message string to HTTPException.__init__ as its `status_code`.
        Exception.__init__(
            self, f"bundle fetch failed with status {status_code}: {detail}"
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(status_code={self.status_code!r}, "
            f"detail={self.detail!r})"
        )


class RetryableBundleError(BundleFetchError):
    """The server said the bundle is temporarily unavailable.

    `retry_after` is the server's `Retry-After` hint in seconds, or None
    if the header was absent or could not be parsed.
    """

    def __init__(
        self, status_code: int, retry_after: Optional[float] = None, detail: str = ""
    ):
        self.retry_after = retry_after
        super().__init__(status_code, detail)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(status_code={self.status_code!r}, "
            f"retry_after={self.retry_after!r}, detail={self.detail!r})"
        )


class NonRetryableBundleError(BundleFetchError):
    """The server said this request cannot succeed; retrying only adds load."""


class BundlePathNotFoundError(NonRetryableBundleError, HTTPException):
    """404 - the requested path is not in the policy repo.

    Inherits `HTTPException` as well so that callers written against the
    pre-existing behaviour (this used to be a bare `fastapi.HTTPException`)
    keep working unchanged, while the retry predicate can still recognise
    it as non-retryable through the single `NonRetryableBundleError` type.
    """

    def __init__(self, detail: str = ""):
        HTTPException.__init__(
            self, status_code=status.HTTP_404_NOT_FOUND, detail=detail
        )
        NonRetryableBundleError.__init__(
            self, status_code=status.HTTP_404_NOT_FOUND, detail=detail
        )


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parses an HTTP `Retry-After` header into seconds from now.

    Accepts both forms allowed by RFC 9110: delta-seconds (we also
    tolerate a float) and an HTTP-date. Returns None when the header is
    missing or cannot be parsed -- a malformed header must never be
    able to stall the client. Negative or past values are clamped to 0.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None

    # delta-seconds
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        pass
    else:
        # "nan"/"inf" parse as floats but are not usable sleep durations
        if not math.isfinite(seconds):
            return None
        return max(seconds, 0.0)

    # HTTP-date
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:  # older pythons return None instead of raising
        return None
    if when.tzinfo is None:
        # An HTTP-date without a timezone is GMT by definition.
        when = when.replace(tzinfo=timezone.utc)
    return max((when - datetime.now(timezone.utc)).total_seconds(), 0.0)


def _retry_after_of(retry_state) -> Optional[float]:
    """The `Retry-After` the last attempt's exception carried, if any."""
    outcome = getattr(retry_state, "outcome", None)
    if outcome is None or not outcome.failed:
        return None
    error = outcome.exception()
    if isinstance(error, RetryableBundleError):
        return error.retry_after
    return None


class wait_retry_after_or_backoff(wait_base):
    """Waits for whichever is longer: the server's `Retry-After` or our
    backoff.

    The server knows how long its clone will take; our backoff exists to
    protect the server from a stampede. Honouring the larger of the two
    respects both.

    `max_retry_after` bounds only the *server-supplied* value, so a
    hostile or buggy header cannot stall the client for hours. It
    deliberately does NOT clamp `base_wait`, which is the operator's own
    POLICY_UPDATER_CONN_RETRY configuration and must keep its meaning.
    """

    def __init__(self, base_wait: wait_base, max_retry_after: float):
        self._base_wait = base_wait
        self._max_retry_after = max_retry_after

    def __call__(self, retry_state) -> float:
        base = self._base_wait(retry_state)
        retry_after = _retry_after_of(retry_state)
        if retry_after is None:
            return base
        return max(min(retry_after, self._max_retry_after), base)


def force_valid_bundle(bundle) -> PolicyBundle:
    try:
        return PolicyBundle(**bundle)
    except ValidationError as e:
        logger.warning(
            "server returned invalid bundle: {err}", bundle=bundle, err=repr(e)
        )
        raise


async def _response_detail(response) -> str:
    """Best-effort extraction of the server's error `detail`.

    Must never raise: it runs on the error path, and a server that
    answered with a non-JSON body (a proxy's HTML 503 page, say) would
    otherwise turn a clean classification into an unclassified
    ValueError.
    """
    try:
        body = await response.json()
    except Exception:
        try:
            return (await response.text())[:512]
        except Exception:
            return ""
    if isinstance(body, dict):
        return str(body.get("detail", body))[:512]
    return str(body)[:512]


class PolicyFetcher:
    """Fetches policy from backend."""

    def __init__(self, backend_url=None, token=None):
        """
        Args:
            backend_url (str): Defaults to opal_client_config.SERVER_URL.
            token ([type], optional): [description]. Defaults to opal_client_config.CLIENT_TOKEN.
        """
        self._token = token or opal_client_config.CLIENT_TOKEN
        self._backend_url = backend_url or opal_client_config.SERVER_URL
        self._auth_headers = tuple_to_dict(get_authorization_header(self._token))

        self._retry_config = (
            opal_client_config.POLICY_UPDATER_CONN_RETRY.toTenacityConfig()
        )
        self._retry_config["reraise"] = True  # This is currently not configurable
        # Never spend attempts on a status the server told us is permanent.
        self._retry_config["retry"] = retry_if_not_exception_type(
            NonRetryableBundleError
        )
        # Honour the server's `Retry-After` on top of the configured backoff.
        self._retry_config["wait"] = wait_retry_after_or_backoff(
            self._retry_config["wait"],
            max_retry_after=opal_client_config.POLICY_UPDATER_MAX_RETRY_AFTER,
        )

        scope_id = opal_client_config.SCOPE_ID

        if scope_id != "default":
            self._policy_endpoint_url = f"{self._backend_url}/scopes/{scope_id}/policy"
        else:
            self._policy_endpoint_url = f"{self._backend_url}/policy"

        # custom SSL context (for self-signed certificates)
        self._custom_ssl_context = get_custom_ssl_context()
        self._ssl_context_kwargs = (
            {"ssl": self._custom_ssl_context}
            if self._custom_ssl_context is not None
            else {}
        )

    @property
    def policy_endpoint_url(self):
        return self._policy_endpoint_url

    async def fetch_policy_bundle(
        self, directories: List[str] = ["."], base_hash: Optional[str] = None
    ) -> Optional[PolicyBundle]:
        attempter = retry(**self._retry_config)(self._fetch_policy_bundle)
        try:
            return await attempter(directories=directories, base_hash=base_hash)
        except Exception as err:
            logger.warning(
                "Failed all attempts to fetch bundle, got error: {err}",
                err=repr(err),
            )
            raise

    async def _classify_response(self, response) -> None:
        """Raises a classified error if the response is one we know about.

        Returns normally for anything else, leaving
        `throw_if_bad_status_code` to apply the pre-existing (retryable)
        behaviour.
        """
        if response.status in RETRYABLE_BUNDLE_STATUSES:
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            detail = await _response_detail(response)
            logger.warning(
                "Bundle fetch retryable ({status}); server asked to retry after {retry_after}s",
                status=response.status,
                retry_after=retry_after,
            )
            raise RetryableBundleError(
                response.status, retry_after=retry_after, detail=detail
            )

        if response.status in NON_RETRYABLE_BUNDLE_STATUSES:
            detail = await _response_detail(response)
            logger.warning(
                "Bundle fetch non-retryable ({status}): {detail}",
                status=response.status,
                detail=detail,
            )
            raise NonRetryableBundleError(response.status, detail=detail)

    async def _fetch_policy_bundle(
        self, directories: List[str] = ["."], base_hash: Optional[str] = None
    ) -> Optional[PolicyBundle]:
        """Fetches the bundle.

        May throw, in which case we retry again -- unless the error is a
        NonRetryableBundleError, which the retry predicate lets through
        immediately.
        """
        params = {"path": directories}
        if base_hash is not None:
            params["base_hash"] = base_hash
        async with aiohttp.ClientSession(
            trust_env=True,
        ) as session:
            logger.info(
                "Fetching policy bundle from {url}",
                url=self._policy_endpoint_url,
            )
            try:
                async with session.get(
                    self._policy_endpoint_url,
                    headers={
                        "content-type": "text/plain",
                        **self._auth_headers,
                    },
                    params=params,
                    **self._ssl_context_kwargs,
                ) as response:
                    if response.status == status.HTTP_404_NOT_FOUND:
                        logger.warning(
                            "requested paths not found: {paths}",
                            paths=directories,
                        )
                        raise BundlePathNotFoundError(
                            detail=f"requested path {self._policy_endpoint_url} was not found in the policy repo!",
                        )

                    # may throw RetryableBundleError / NonRetryableBundleError
                    await self._classify_response(response)

                    # may throw ValueError
                    await throw_if_bad_status_code(
                        response, expected=[status.HTTP_200_OK], logger=logger
                    )

                    # may throw Validation Error
                    bundle = await response.json()
                    bundle = force_valid_bundle(bundle)
                    logger.info("Fetched valid bundle, id: {id}", id=bundle.hash)

                    return bundle
            except aiohttp.ClientError as e:
                logger.warning("server connection error: {err}", err=repr(e))
                raise
