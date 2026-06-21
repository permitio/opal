import re
from typing import Union
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp
import httpx

#: Query-string parameter names whose values may carry credentials.
SENSITIVE_QUERY_PARAMS = frozenset(
    {
        "token",
        "access_token",
        "api_key",
        "apikey",
        "key",
        "password",
        "secret",
        "sig",
        "signature",
    }
)

#: Matches ``scheme://userinfo@`` anywhere in free text.
_USERINFO_RE = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)[^/@\s]+@")


def redact_url(url: str) -> str:
    """Strip embedded credentials from a URL so it is safe to log.

    Data source / policy repo URLs may be of the form
    ``https://user:token@host/path`` or carry a credential in a query parameter
    (e.g. ``?token=...``). We replace any ``user:password@`` userinfo with
    ``***@`` and mask the values of known sensitive query parameters, while
    keeping the host, port, path and non-sensitive params intact for debugging.
    Returns the input byte-for-byte unchanged if it is empty, cannot be parsed,
    or carries nothing sensitive.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    changed = False
    netloc = parts.netloc
    if parts.username or parts.password:
        host = parts.hostname or ""
        if ":" in host:  # IPv6 literal - urlsplit strips the surrounding brackets
            host = f"[{host}]"
        if parts.port is not None:
            host = f"{host}:{parts.port}"
        netloc = f"***@{host}"
        changed = True

    query = parts.query
    if query:
        pairs = parse_qsl(query, keep_blank_values=True)
        if any(key.lower() in SENSITIVE_QUERY_PARAMS for key, _ in pairs):
            query = urlencode(
                [
                    (key, "***" if key.lower() in SENSITIVE_QUERY_PARAMS else value)
                    for key, value in pairs
                ],
                safe="*",
            )
            changed = True

    if not changed:
        return url
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def redact_url_in_text(text: str, url: str = "") -> str:
    """Redact embedded credentials from free text such as a git error message.

    Scrubs any ``scheme://user:password@`` userinfo found anywhere in the text
    (a regex, so it is robust to the exact URL form git happens to print), and
    additionally replaces verbatim occurrences of ``url`` with its fully redacted
    form so query-string tokens of a known URL are masked too.
    """
    if not text:
        return text
    scrubbed = _USERINFO_RE.sub(lambda m: f"{m.group('scheme')}***@", text)
    if url:
        scrubbed = scrubbed.replace(url, redact_url(url))
    return scrubbed


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
