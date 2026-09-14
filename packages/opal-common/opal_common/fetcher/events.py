from typing import ClassVar, List, Optional, Set

from opal_common.logging_utils.redaction import RedactedReprMixin
from pydantic import BaseModel, Field, field_validator


class FetcherConfig(RedactedReprMixin, BaseModel):
    """The configuration of a fetcher, used as part of a FetchEvent Fetch
    Provider's have their own unique events and configurations.

    Configurations

    Note: subclasses commonly carry credentials (e.g. auth headers). They must
    list any secret-bearing fields in ``_redacted_repr_fields`` so they never
    leak into logs - see ``RedactedReprMixin``.
    """

    fetcher: Optional[str] = Field(
        None,
        description="indicates to OPAL client that it should use a custom FetcherProvider to fetch the data",
    )


class FetchEvent(RedactedReprMixin, BaseModel):
    """Event used to describe an queue fetching tasks Design note -

    By using a Pydantic model - we can create a potentially transfer FetchEvents to be handled by other network nodes (perhaps via RPC)
    """

    # ``config`` may carry a FetcherConfig with credentials - mask it in repr/str.
    _redacted_repr_fields: ClassVar[Set[str]] = {"config"}
    # ``url`` can embed credentials (``user:token@host`` / ``?token=``); strip
    # them via redact_url while keeping host/path visible for debugging.
    _redacted_url_fields: ClassVar[Set[str]] = {"url"}

    # Event id to be filled by the engine
    id: Optional[str] = None
    # optional name of the specific event
    name: Optional[str] = None
    # A string identifying the fetcher class to use (as registered in the fetcher register)
    fetcher: str
    # The url the event targets for fetching
    url: str
    # Specific fetcher configuration (overridden by deriving event classes (FetcherConfig)
    config: Optional[dict] = None
    # Tenacity.retry - Override default retry configuration for this event
    retry: Optional[dict] = None

    @field_validator("config", mode="before")
    @classmethod
    def _coerce_model_config(cls, value):
        """Accept a ``FetcherConfig`` where a plain ``dict`` is declared.

        pydantic v1 silently coerced a BaseModel into a ``dict`` field (it fell
        back to ``dict(model)``); v2 rejects it with a ``dict_type`` error.
        Callers legitimately pass a config *model* here - notably
        ``FetchingEngine.queue_url(url, callback, HttpFetcherConfig(...))`` -
        so keep the v1 contract. Subclasses that re-declare ``config`` with a
        concrete model type just re-validate the resulting mapping, which is
        lossless for these flat config models.
        """
        if isinstance(value, BaseModel):
            return dict(value)
        return value
