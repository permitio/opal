"""Types for conditional fetching (HTTP ``ETag`` / ``Last-Modified``).

A fetch provider is created per fetch, so it stays stateless: the caller passes
the validators it got last time on the ``FetchEvent`` and gets the new ones back
with the result. Providers only return these types when conditional fetching is
enabled in their config, so callers that don't opt in see no change.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class CacheValidators(BaseModel):
    """The validators a server returned for a resource."""

    model_config = ConfigDict(hide_input_in_errors=True)

    etag: Optional[str] = None
    last_modified: Optional[str] = None

    def is_empty(self) -> bool:
        return self.etag is None and self.last_modified is None

    def to_request_headers(self) -> Dict[str, str]:
        """The conditional request headers for these validators."""
        headers = {}
        if self.etag is not None:
            headers["If-None-Match"] = self.etag
        if self.last_modified is not None:
            headers["If-Modified-Since"] = self.last_modified
        return headers


@dataclass
class ValidatedData:
    """Fetched data, together with the validators that came with it."""

    data: Any
    validators: CacheValidators


@dataclass
class NotModified:
    """The server confirmed (``304``) that the resource has not changed.

    Returned instead of ``None``, which callers treat as a failed fetch.
    """

    validators: CacheValidators
