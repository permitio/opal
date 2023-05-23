from enum import Enum

from opal_client.engine.options import CedarServerOptions, OpaServerOptions
from opal_client.policy.options import PolicyConnRetryOptions
from opal_client.policy_store.schemas import PolicyStoreAuth, PolicyStoreTypes
from opal_common.config import opal_common_config
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.schemas.data import DEFAULT_DATA_TOPIC, UpdateCallback
from pydantic import BaseSettings, Field, validator


# Opal Client general configuration -------------------------------------------
class EngineLogFormat(str, Enum):
    NONE = "none"  # no opa logs are piped
    MINIMAL = "minimal"  # only the event name is logged
    HTTP = "http"  # tries to extract http method, path and response status code
    FULL = "full"  # logs the entire data dict returned


class OpalClientConfig(BaseSettings):
    class Config:
        env_prefix = "OPAL_"

    # opa client (policy store) configuration
    POLICY_STORE_TYPE: PolicyStoreTypes = PolicyStoreTypes.OPA
    POLICY_STORE_URL: str = "http://localhost:8181"

    POLICY_STORE_AUTH_TYPE: PolicyStoreAuth = PolicyStoreAuth.NONE
    POLICY_STORE_AUTH_TOKEN: str = Field(
        None,
        description="the authentication (bearer) token OPAL client will use to "
        "authenticate against the policy store (i.e: OPA agent).",
    )
    POLICY_STORE_AUTH_OAUTH_SERVER: str = Field(
        None,
        description="the authentication server OPAL client will use to authenticate against for retrieving the access_token.",
    )
    POLICY_STORE_AUTH_OAUTH_CLIENT_ID: str = Field(
        None,
        description="the client_id OPAL will use to authenticate against the OAuth server.",
    )
    POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET: str = Field(
        None,
        description="the client secret OPAL will use to authenticate against the OAuth server.",
    )

    POLICY_STORE_CONN_RETRY: PolicyConnRetryOptions = Field(
        # defaults are being set according to PolicyStoreConnRetryOptions pydantic definitions (see class)
        {},
        description="retry options when connecting to the policy store (i.e. the agent that handles the policy, e.g. OPA)",
    )
    POLICY_UPDATER_CONN_RETRY: PolicyConnRetryOptions = Field(
        {
            "wait_strategy": "random_exponential",
            "max_wait": 10,
            "attempts": 5,
            "wait_time": 1,
        },
        description="retry options when connecting to the policy source (e.g. the policy bundle server)",
    )

    POLICY_STORE_POLICY_PATHS_TO_IGNORE: list = Field(
        [],
        description="When loading policies manually or otherwise externally into the policy store, use this list of glob patterns to have OPAL ignore and not delete or override them, end paths (without any wildcards in the middle) with '\**' to indicate you want all nested under the path to be ignored",
    )

    # create an instance of a policy store upon load
    def load_policy_store():
        from opal_client.policy_store.policy_store_client_factory import (
            PolicyStoreClientFactory,
        )

        return PolicyStoreClientFactory.create()

    # opa runner configuration (OPA can optionally be run by OPAL) ----------------

    # whether or not OPAL should run OPA by itself in the same container
    INLINE_OPA_ENABLED: bool = True

    # if inline OPA is indeed enabled, user can pass cli options
    # (configuration) that affects how OPA will run
    INLINE_OPA_CONFIG: OpaServerOptions = Field(
        {},  # defaults are being set according to OpaServerOptions pydantic definitions (see class)
        description="cli options used when running `opa run --server` inline",
    )

    INLINE_OPA_LOG_FORMAT: EngineLogFormat = EngineLogFormat.NONE

    # Cedar runner configuration (Cedar-engine can optionally be run by OPAL) ----------------

    # whether or not OPAL should run the Cedar agent by itself in the same container
    INLINE_CEDAR_ENABLED: bool = True

    # if inline Cedar is indeed enabled, user can pass cli options
    # (configuration) that affects how the agent will run
    INLINE_CEDAR_CONFIG: CedarServerOptions = Field(
        {},  # defaults are being set according to CedarServerOptions pydantic definitions (see class)
        description="cli options used when running the Cedar agent inline",
    )

    INLINE_CEDAR_LOG_FORMAT: EngineLogFormat = EngineLogFormat.NONE

    # configuration for fastapi routes
    ALLOWED_ORIGINS = ["*"]

    # general configuration for pub/sub clients
    KEEP_ALIVE_INTERVAL: int = 0

    # Opal Server general configuration -------------------------------------------

    # opal server url
    SERVER_URL: str = Field("http://localhost:7002", flags=["-s"])
    # opal server pubsub url
    SERVER_WS_URL: str = None

    @validator("SERVER_WS_URL", pre=True)
    def server_ws_url(cls, v, values):
        if v is None:
            return values["SERVER_URL"].replace("https", "wss").replace("http", "ws")
        return v

    SERVER_PUBSUB_URL: str = None

    @validator("SERVER_PUBSUB_URL", pre=True)
    def server_pubsub_url(cls, v, values):
        if v is None:
            return f"{values['SERVER_WS_URL']}/ws"
        return v

    # opal server auth token
    CLIENT_TOKEN: str = Field(
        "THIS_IS_A_DEV_SECRET",
        description="opal server auth token",
        flags=["-t"],
    )

    # client-api server
    CLIENT_API_SERVER_WORKER_COUNT: int = Field(
        1,
        description="(if run via CLI) Worker count for the opal-client's internal server",
    )

    CLIENT_API_SERVER_HOST: str = Field(
        "127.0.0.1",
        description="(if run via CLI)  Address for the opal-client's internal server to bind",
    )

    CLIENT_API_SERVER_PORT: int = Field(
        7000,
        description="(if run via CLI)  Port for the opal-client's internal server to bind",
    )

    WAIT_ON_SERVER_LOAD: bool = Field(
        False,
        description="If set, client would wait for 200 from server's loadlimit endpoint before starting background tasks",
    )

    # Policy updater configuration ------------------------------------------------

    # directories in policy repo we should subscribe to for policy code (rego) modules
    POLICY_SUBSCRIPTION_DIRS: list = Field(
        ["."],
        delimiter=":",
        description="directories in policy repo we should subscribe to",
    )

    # Data updater configuration --------------------------------------------------
    DATA_UPDATER_ENABLED: bool = Field(
        True,
        description="If set to False, opal client will not listen to dynamic data updates. "
        "Dynamic data fetching will be completely disabled.",
    )

    DATA_TOPICS: list = Field(
        [DEFAULT_DATA_TOPIC],
        description="Data topics to subscribe to",
    )

    DEFAULT_DATA_SOURCES_CONFIG_URL: str = Field(
        None,
        description="Default URL to fetch data configuration from",
    )

    @validator("DEFAULT_DATA_SOURCES_CONFIG_URL", pre=True)
    def default_data_sources_config_url(cls, v, values):
        if v is None:
            return f"{values['SERVER_URL']}/data/config"
        return v

    DEFAULT_DATA_URL: str = Field(
        "http://localhost:8000/policy-config",
        description="Default URL to fetch data from",
    )

    SHOULD_REPORT_ON_DATA_UPDATES: bool = Field(
        False,
        description="Should the client report on updates to callbacks defined in "
        "DEFAULT_UPDATE_CALLBACKS or within the given updates",
    )
    DEFAULT_UPDATE_CALLBACK_CONFIG: HttpFetcherConfig = Field(
        {
            "method": "post",
            "headers": {"content-type": "application/json"},
            "process_data": False,
        },
    )
    # HERE:
    DEFAULT_UPDATE_CALLBACKS: UpdateCallback = Field(
        None,
        description="Where/How the client should report on the completion of data updates",
    )

    @validator("DEFAULT_UPDATE_CALLBACKS", pre=True)
    def default_update_callbacks(cls, v, values):
        if v is None:
            return UpdateCallback(
                callbacks=[f"{values['SERVER_URL']}/data/callback_report"]
            )
        return v

    # OPA transaction log / healthcheck policy ------------------------------------
    OPA_HEALTH_CHECK_POLICY_ENABLED: bool = Field(
        False,
        description="Should we load a special healthcheck policy into OPA that checks "
        + "that opa was synced correctly and is ready to answer to authorization queries",
    )

    OPA_HEALTH_CHECK_TRANSACTION_LOG_PATH: str = Field(
        "system/opal/transactions",
        description="Path to OPA document that stores the OPA write transactions",
    )

    OPAL_CLIENT_STAT_ID: str = Field(
        None,
        description="Unique client statistics identifier",
    )

    OPA_HEALTH_CHECK_POLICY_PATH = "engine/healthcheck/opal.rego"

    SCOPE_ID: str = Field("default", description="OPAL Scope ID")

    STORE_BACKUP_PATH: str = Field(
        "/opal/backup/opa.json",
        description="Path to backup policy store's data to",
    )
    STORE_BACKUP_INTERVAL: int = Field(
        60,
        description="Interval in seconds to backup policy store's data",
    )
    OFFLINE_MODE_ENABLED: bool = Field(
        False,
        description="If set, opal client will try to load policy store from backup file and operate even if server is unreachable. Ignored if INLINE_OPA_ENABLED=False",
    )
    SPLIT_ROOT_DATA: bool = Field(
        False, description="Split writing data updates to root path"
    )

    def on_load(self):
        # LOGGER
        if self.INLINE_OPA_LOG_FORMAT == EngineLogFormat.NONE:
            opal_common_config.LOG_MODULE_EXCLUDE_LIST.append("opal_client.opa.logger")
            # re-assign to apply to internal confi-entries as well
            opal_common_config.LOG_MODULE_EXCLUDE_LIST = (
                opal_common_config.LOG_MODULE_EXCLUDE_LIST
            )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.on_load()


opal_client_config = OpalClientConfig()
