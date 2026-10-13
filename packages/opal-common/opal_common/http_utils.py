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

#: Matches ``?token=value`` (or ``&``/``#``/``;``) for a sensitive param in free text.
_SENSITIVE_PARAM_RE = re.compile(
    r"(?P<prefix>[?&#;](?:"
    + "|".join(sorted(SENSITIVE_QUERY_PARAMS))
    + r")=)[^\s&#;'\"<>\\)\]}]*",
    re.IGNORECASE,
)

#: An Authorization header value as rendered by a dict/multidict repr or JSON
#: (including JSON embedded in a JSON string, hence the optional backslash).
_QUOTED_AUTH_HEADER_RE = re.compile(
    r"(?P<prefix>(?P<q>\\?[\"'])(?:proxy-)?authorization(?P=q)\s*:\s*(?P<vq>\\?[\"']))"
    r".*?(?P=vq)",
    re.IGNORECASE,
)

#: An Authorization header in ``name: value`` form; the value is an optional auth
#: scheme plus one token.
_HEADER_AUTH_RE = re.compile(
    r"(?P<prefix>\b(?:proxy-)?authorization\s*:\s*)"
    r"(?:(?:bearer|basic|token|digest)\s+)?[^\s'\",;\\]+",
    re.IGNORECASE,
)

#: A ``Bearer``/``Basic`` credential anywhere in free text.
_AUTH_SCHEME_RE = re.compile(
    r"(?P<prefix>\b(?:bearer|basic)\s+)(?P<token>[A-Za-z0-9][A-Za-z0-9\-._~+/]*=*)",
    re.IGNORECASE,
)


def _mask_auth_scheme_token(match: "re.Match[str]") -> str:
    token = match.group("token")
    # A lowercase word is prose ("Bearer token is not valid"), not a credential.
    if token.isalpha() and token.islower():
        return match.group(0)
    return f"{match.group('prefix')}***"


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
    form, then scrubs any remaining ``scheme://user:password@`` userinfo and
    the values of ``SENSITIVE_QUERY_PARAMS`` (``?token=...``, ``&key=...``)
    found anywhere in the text - regexes, so they are robust to the exact URL
    form git or aiohttp happens to print.

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
    scrubbed = _SENSITIVE_PARAM_RE.sub(lambda m: f"{m.group('prefix')}***", scrubbed)
    return scrubbed


def redact_sensitive_text(text: str) -> str:
    """Mask credentials anywhere in free text, e.g. a formatted log record.

    On top of ``redact_url_in_text`` this masks Authorization /
    Proxy-Authorization header values - as rendered in dict and multidict
    reprs (``'Authorization': '...'``), JSON (``"Authorization": "..."``) and
    header form (``Authorization: ...``) - and ``Bearer``/``Basic`` credentials
    wherever they appear. Matching is case-insensitive and the result is
    idempotent.

    Never raises: this runs on every log record, so a non-string input is
    returned unchanged rather than breaking logging.
    """
    if not text or not isinstance(text, str):
        return text
    scrubbed = redact_url_in_text(text)
    scrubbed = _QUOTED_AUTH_HEADER_RE.sub(
        lambda m: f"{m.group('prefix')}***{m.group('vq')}", scrubbed
    )
    scrubbed = _HEADER_AUTH_RE.sub(lambda m: f"{m.group('prefix')}***", scrubbed)
    return _AUTH_SCHEME_RE.sub(_mask_auth_scheme_token, scrubbed)


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
