from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple, Union

from opal_common.fetcher.events import coerce_config_model_to_dict
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.logging_utils.redaction import RedactedReprMixin
from opal_common.schemas.store import JSONPatchAction
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

JsonableValue = Union[List[JSONPatchAction], List[Any], Dict[str, Any]]


DEFAULT_DATA_TOPIC = "policy_data"


class DataSourceEntry(RedactedReprMixin, BaseModel):
    """
    Data source configuration - where client's should retrieve data from and how they should store it
    """

    # ``config`` may carry fetcher auth (e.g. Authorization headers) and
    # ``data`` an inline payload - mask both in repr/str so they never leak into
    # logs (entries are frequently interpolated into log messages).
    _redacted_repr_fields: ClassVar[Set[str]] = {"config", "data"}
    # ``url`` can embed credentials (``user:token@host`` / ``?token=``); strip
    # them via redact_url while keeping host/path visible for debugging.
    _redacted_url_fields: ClassVar[Set[str]] = {"url"}

    @field_validator("config", mode="before")
    @classmethod
    def _coerce_model_config(cls, value):
        """Accept a ``FetcherConfig`` where a plain ``dict`` is declared.

        ``DataSourceEntry(config=HttpFetcherConfig(...))`` is the pattern
        ``configure_external_data_sources.mdx`` tells integrators to use.
        """
        return coerce_config_model_to_dict(cls, value)

    @field_validator("data")
    @classmethod
    def validate_save_method(cls, value, info: ValidationInfo):
        save_method = info.data.get("save_method")
        if save_method not in ["PUT", "PATCH"]:
            raise ValueError("'save_method' must be either PUT or PATCH")
        if save_method == "PATCH" and (
            not isinstance(value, list)
            or not all(isinstance(elem, JSONPatchAction) for elem in value)
        ):
            # NOTE: raise ValueError (not TypeError) - pydantic v2 only wraps
            # ValueError/AssertionError into a ValidationError, while v1 also
            # wrapped TypeError. This keeps the v1 caller contract.
            raise ValueError(
                "'data' must be of type JSON patch request when save_method is PATCH"
            )
        return value

    # How to obtain the data
    url: str = Field(..., description="Url source to query for data")
    config: Optional[dict] = Field(
        None,
        description="Suggested fetcher configuration (e.g. auth or method) to fetch data with",
    )
    # How to catalog data
    topics: List[str] = Field(
        [DEFAULT_DATA_TOPIC], description="topics the data applies to"
    )
    # How to save the data
    # see https://www.openpolicyagent.org/docs/latest/rest-api/#data-api path is the path nested under <OPA_SERVER>/<version>/data
    dst_path: str = Field("", description="OPA data api path to store the document at")
    save_method: str = Field(
        "PUT",
        description="Method used to write into OPA - PUT/PATCH, when using the PATCH method the data field should conform to the JSON patch schema defined in RFC 6902(https://datatracker.ietf.org/doc/html/rfc6902#section-3)",
    )
    data: Optional[JsonableValue] = Field(
        None,
        # ``JsonableValue`` is an ordered union: a JSON-patch list must win over
        # the catch-all ``List[Any]``. pydantic v2 defaults to "smart" union
        # mode, which would match ``List[Any]`` first and leave raw dicts -
        # breaking the ``isinstance(elem, JSONPatchAction)`` check below and the
        # PATCH save_method path. v1 semantics == left-to-right.
        union_mode="left_to_right",
        description="Data payload to embed within the data update (instead of having "
        "the client fetch it from the url).",
    )


class DataSourceEntryWithPollingInterval(DataSourceEntry):
    # Periodic Update Interval
    # If set, tells OPAL server how frequently to send message to clients that they need to refresh their data store from a data source
    # Time in Seconds
    periodic_update_interval: Optional[float] = Field(
        None, description="Polling interval to refresh data from data source"
    )


class DataSourceConfig(BaseModel):
    """Static list of Data Source Entries returned to client.

    Answers this question for the client: from where should i get the
    full picture of data i need? (as opposed to incremental data
    updates)
    """

    entries: List[DataSourceEntryWithPollingInterval] = Field(
        [], description="list of data sources and how to fetch from them"
    )

    @field_validator("entries", mode="before")
    @classmethod
    def _accept_base_entries(cls, value):
        """Accept plain ``DataSourceEntry`` instances in the list.

        ``DataSourceEntryWithPollingInterval`` is a strict superset of
        ``DataSourceEntry`` - it only adds the optional
        ``periodic_update_interval`` - and pydantic v1 validated a parent
        instance into the child by reading its fields. v2 requires an instance
        of the declared type or a mapping, which broke the
        ``DataSourceConfig(entries=[DataSourceEntry(...)])`` form used in
        ``configure_external_data_sources.mdx``. Flattening the parent is
        lossless; an instance that is already the child type is left alone.
        """
        if not isinstance(value, (list, tuple)):
            return value
        return [
            (
                dict(entry)
                if isinstance(entry, DataSourceEntry)
                and not isinstance(entry, DataSourceEntryWithPollingInterval)
                else entry
            )
            for entry in value
        ]


class ServerDataSourceConfig(BaseModel):
    """As its data source configuration, the server can either hold:

    1) A static DataSourceConfig returned to all clients regardless of
    identity. If all clients need the same config, this is the way to
    go.

    2) A redirect url (external_source_url), to which the opal client
    will be redirected when requesting its DataSourceConfig. The client
    will issue the same request (with the same headers, including the
    JWT token identifying it) to the url configured. This option is good
    if each client must receive a different base data configuration, for
    example for a multi-tenant deployment.

    By providing the server that serves external_source_url the value of
    OPAL_AUTH_PUBLIC_KEY, that server can validate the JWT and get it's
    claims, in order to apply authorization and/or other conditions
    before returning the data sources relevant to said client.
    """

    config: Optional[DataSourceConfig] = Field(
        None, description="static list of data sources and how to fetch from them"
    )
    external_source_url: Optional[AnyHttpUrl] = Field(
        None,
        description="external url to serve data sources dynamically."
        + " if set, the clients will be redirected to this url when requesting to fetch data sources.",
    )

    @model_validator(mode="after")
    def check_passwords_match(self):
        config, redirect_url = self.config, self.external_source_url
        if config is None and redirect_url is None:
            raise ValueError(
                "you must provide one of these fields: config, external_source_url"
            )
        if config is not None and redirect_url is not None:
            raise ValueError(
                "you must provide ONLY ONE of these fields: config, external_source_url"
            )
        return self


class CallbackEntry(BaseModel):
    """An entry in the callbacks register.

    this schema is used by the callbacks api
    """

    key: Optional[str] = Field(
        None, description="unique id to identify this callback (optional)"
    )
    url: str = Field(..., description="http/https url to call back on update")
    config: Optional[HttpFetcherConfig] = Field(
        None,
        description="optional http config for the target url (i.e: http method, headers, etc)",
    )


class UpdateCallback(BaseModel):
    """Configuration of callbacks upon completion of a FetchEvent Allows
    notifying other services on the update flow.

    Each callback is either a URL (str) or a tuple of a url and
    HttpFetcherConfig defining how to approach the URL
    """

    callbacks: List[Union[str, Tuple[str, HttpFetcherConfig]]]


class DataUpdate(BaseModel):
    """DataSources used as OPAL-server configuration Data update sent to
    clients."""

    # a UUID to identify this update (used as part of an updates complition callback)
    id: Optional[str] = None
    entries: List[DataSourceEntry] = Field(
        ..., description="list of related updates the OPAL client should perform"
    )
    reason: Optional[str] = Field(None, description="Reason for triggering the update")
    # Configuration for how to notify other services on the status of Update
    callback: UpdateCallback = UpdateCallback(callbacks=[])


class DataEntryReport(BaseModel):
    """A report of the processing of a single DataSourceEntry."""

    entry: DataSourceEntry = Field(..., description="The entry that was processed")
    # Was the entry successfully fetched
    fetched: Optional[bool] = False
    # Was the entry successfully saved into the policy-data-store
    saved: Optional[bool] = False
    # Hash of the returned data
    hash: Optional[str] = None


class DataUpdateReport(BaseModel):
    # the UUID of the update this report is for
    update_id: Optional[str] = None
    # Each DataSourceEntry and how it was processed
    reports: List[DataEntryReport]
    # in case this is a policy update, the new hash committed the policy store.
    policy_hash: Optional[str] = None
    user_data: Dict[str, Any] = {}
