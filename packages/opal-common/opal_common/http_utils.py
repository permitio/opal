from typing import Union
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import httpx


def redact_url(url: str) -> str:
    """Strip any embedded credentials (``user:password@``) from a URL so it is
    safe to log.

    Data source / policy repo URLs may be of the form
    ``https://user:token@host/path``. Logging them verbatim leaks the
    credentials, so we replace the userinfo component with ``***`` while keeping
    the rest of the URL intact for debugging. Returns the input unchanged if it
    cannot be parsed or carries no credentials.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.username and not parts.password:
        return url
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    netloc = f"***@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def is_http_error_response(
    response: Union[aiohttp.ClientResponse, httpx.Response]
) -> bool:
    """HTTP 400 and above are considered error responses."""
    status: int = (
        response.status
        if isinstance(response, aiohttp.ClientResponse)
        else response.status_code
    )

    return status >= 400
