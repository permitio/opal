from typing import Any, ClassVar, List, Optional, Set, get_args

from opal_common.logging_utils.redaction import RedactedReprMixin
from pydantic import BaseModel, Field, field_validator


def _declared_types(annotation: Any) -> tuple:
    """Flattens ``Optional[X]`` / ``Union[X, Y]`` into its concrete members."""
    args = get_args(annotation)
    if not args:
        return (annotation,)
    return tuple(arg for arg in args if arg is not type(None))


def coerce_config_model_to_dict(cls, value: Any, field_name: str = "config") -> Any:
    """Accept a config *model* where a plain ``dict`` is declared.

    pydantic v1 silently coerced a BaseModel into a ``dict`` field (falling back
    to ``dict(model)``); v2 rejects it with a ``dict_type`` error. Callers
    legitimately pass a config model - notably
    ``FetchingEngine.queue_url(url, callback, HttpFetcherConfig(...))`` and the
    ``DataSourceEntry(config=HttpFetcherConfig(...))`` pattern in
    ``configure_external_data_sources.mdx`` - so keep the v1 contract.

    Only coerce when the field actually declares a plain ``dict``. Subclasses
    that re-declare ``config`` with a concrete model type (``HttpFetchEvent``,
    and every third-party provider event) must be left alone: v1 never
    re-validated a model instance there, and flattening it would
    - drop fields a subclass added on top of the declared type, and
    - blank fields that are alias-only, since ``dict(model)`` yields field
      names and a model without ``populate_by_name`` cannot read them back.
    Both are silent - the provider would then fetch with empty credentials.
    """
    if not isinstance(value, BaseModel):
        return value

    field = cls.model_fields.get(field_name)
    if field is not None:
        declared = _declared_types(field.annotation)
        if any(
            isinstance(declared_type, type) and issubclass(declared_type, BaseModel)
            for declared_type in declared
        ):
            return value

    # Shallow, matching v1's ``dict(model)`` exactly: nested models stay models
    # and enums stay enums.
    return dict(value)


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
        """Accept a ``FetcherConfig`` where a plain ``dict`` is declared."""
        return coerce_config_model_to_dict(cls, value)
