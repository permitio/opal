from typing import Optional
from urllib.parse import quote


def normalize_broadcaster_uri(uri: Optional[str]) -> Optional[str]:
    """Percent-encode special characters in broadcaster URI userinfo
    credentials.

    Postgres and Redis broadcaster backends parse the connection URI with
    ``urllib.parse.urlsplit`` and ``urllib.parse.unquote``. When a password
    contains raw ``%`` sequences (such as ``bnvcGy1pU%071lS``, where ``%07``
    decodes to ASCII BEL) or unescaped URI delimiters (``@``, ``:``, ``/``,
    ``?``, ``#``), backend connection establishment fails and closes client
    websocket connections immediately after opening.
    """
    if not uri or "://" not in uri:
        return uri
    scheme, remainder = uri.split("://", 1)
    if "@" not in remainder:
        return uri
    userinfo, host_and_path = remainder.rsplit("@", 1)
    encoded_userinfo = _encode_userinfo(userinfo)
    return f"{scheme}://{encoded_userinfo}@{host_and_path}"


def _encode_userinfo(userinfo: str) -> str:
    if ":" not in userinfo:
        return quote(userinfo, safe="")
    username, password = userinfo.split(":", 1)
    return f"{quote(username, safe='')}:{quote(password, safe='')}"
