import re
from typing import Tuple, Union
from urllib.parse import urlsplit, urlunsplit

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


def _mask_sensitive_params(component: str) -> Tuple[str, bool]:
    """Mask values of known sensitive params in a raw query/fragment component.

    Operates directly on the raw ``key=value&...`` text (rather than
    ``parse_qsl`` + ``urlencode``) so the encoding of untouched params is
    preserved byte-for-byte - only the sensitive values are replaced with
    ``***``. Returns the (possibly rewritten) component and whether anything
    changed.
    """
    changed = False
    out = []
    for pair in component.split("&"):
        key, sep, _ = pair.partition("=")
        if sep and key.lower() in SENSITIVE_QUERY_PARAMS:
            out.append(f"{key}=***")
            changed = True
        else:
            out.append(pair)
    return "&".join(out), changed


def redact_url(url: str) -> str:
    """Strip embedded credentials from a URL so it is safe to log.

    Data source / policy repo URLs may be of the form
    ``https://user:token@host/path`` or carry a credential in a query parameter
    (e.g. ``?token=...``). We replace any ``user:password@`` userinfo with
    ``***@`` and mask the values of known sensitive query (and fragment)
    parameters, while keeping the host, port, path and non-sensitive params
    intact for debugging. Returns the input byte-for-byte unchanged if it is
    empty, cannot be parsed, or carries nothing sensitive.

    Never raises: this helper is called from log/except paths, so any parsing
    error yields the input unchanged rather than propagating.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    changed = False
    netloc = parts.netloc
    try:
        if parts.username or parts.password:
            host = parts.hostname or ""
            if ":" in host:  # IPv6 literal - urlsplit strips the surrounding brackets
                host = f"[{host}]"
            if parts.port is not None:
                host = f"{host}:{parts.port}"
            netloc = f"***@{host}"
            changed = True
    except ValueError:
        # ``urlsplit`` is lazy - accessing ``.username``/``.password``/``.port``
        # is what actually validates and can raise (e.g. "Port out of range").
        # We must never throw from a log path, so bail out unchanged.
        return url

    query, query_changed = _mask_sensitive_params(parts.query)
    fragment, fragment_changed = _mask_sensitive_params(parts.fragment)
    changed = changed or query_changed or fragment_changed

    if not changed:
        return url
    return urlunsplit((parts.scheme, netloc, parts.path, query, fragment))


def redact_url_in_text(text: str, url: str = "") -> str:
    """Redact embedded credentials from free text such as a git error message.

    Replaces verbatim occurrences of a known ``url`` with its fully redacted
    form (so query-string tokens of that URL are masked too), then scrubs any
    remaining ``scheme://user:password@`` userinfo found anywhere in the text
    (a regex, so it is robust to the exact URL form git happens to print).

    The known-URL replacement runs *first*: the regex rewrites
    ``user:pw@`` -> ``***@``, which would otherwise destroy the verbatim ``url``
    before its query tokens could be masked.
    """
    if not text:
        return text
    scrubbed = text
    if url:
        scrubbed = scrubbed.replace(url, redact_url(url))
    scrubbed = _USERINFO_RE.sub(lambda m: f"{m.group('scheme')}***@", scrubbed)
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
