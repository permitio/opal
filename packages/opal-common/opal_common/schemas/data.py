from logging import basicConfig
from pydoc import describe
from typing import Any, Dict, List, Optional, Tuple, Union

from opal_common.fetcher.events import FetcherConfig
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.schemas.store import JSONPatchAction
from pydantic import AnyHttpUrl, BaseModel, Field, root_validator, validator

JsonableValue = Union[List[JSONPatchAction], List[Any], Dict[str, Any]]


DEFAULT_DATA_TOPIC = "policy_data"


class DataSourceEntry(BaseModel):
    """
    Data source configuration - where client's should retrieve data from and how they should store it
    """

    @validator("data")
    def validate_save_method(cls, value, values):
        if values["save_method"] not in ["PUT", "PATCH"]:
            raise ValueError("'save_method' must be either PUT or PATCH")
        if values["save_method"] == "PATCH" and (
            not isinstance(value, list)
            or not all(isinstance(elem, JSONPatchAction) for elem in value)
        ):
            raise TypeError(
                "'data' must be of type JSON patch request when save_method is PATCH"
            )
        return value

    # How to obtain the data
    url: str = Field(..., description="Url source to query for data")
    config: dict = Field(
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

    @root_validator
    def check_passwords_match(cls, values):
        config, redirect_url = values.get("config"), values.get("external_source_url")
        if config is None and redirect_url is None:
            raise ValueError(
                "you must provide one of these fields: config, external_source_url"
            )
        if config is not None and redirect_url is not None:
            raise ValueError(
                "you must provide ONLY ONE of these fields: config, external_source_url"
            )
        return values


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
    reason: str = Field(None, description="Reason for triggering the update")
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
