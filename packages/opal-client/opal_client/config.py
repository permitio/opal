from enum import Enum

from opal_client.engine.options import CedarServerOptions, OpaServerOptions
from opal_client.policy.options import ConnRetryOptions
from opal_client.policy_store.schemas import PolicyStoreAuth, PolicyStoreTypes
from opal_common.confi import Confi, confi
from opal_common.config import opal_common_config
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.schemas.data import DEFAULT_DATA_TOPIC, UpdateCallback


# Opal Client general configuration -------------------------------------------
class EngineLogFormat(str, Enum):
    NONE = "none"  # no opa logs are piped
    MINIMAL = "minimal"  # only the event name is logged
    HTTP = "http"  # tries to extract http method, path and response status code
    FULL = "full"  # logs the entire data dict returned


class OpalClientConfig(Confi):
    # opa client (policy store) configuration
    POLICY_STORE_TYPE = confi.enum(
        "POLICY_STORE_TYPE",
        PolicyStoreTypes,
        PolicyStoreTypes.OPA,
        description="The type of policy store to use (e.g., OPA, Cedar, etc.)",
    )
    POLICY_STORE_URL = confi.str(
        "POLICY_STORE_URL",
        "http://localhost:8181",
        description="The URL of the policy store (e.g., OPA agent).",
    )

    POLICY_STORE_AUTH_TYPE = confi.enum(
        "POLICY_STORE_AUTH_TYPE",
        PolicyStoreAuth,
        PolicyStoreAuth.NONE,
        description="The authentication type to use for the policy store (e.g., NONE, TOKEN, etc.)",
    )
    POLICY_STORE_AUTH_TOKEN = confi.str(
        "POLICY_STORE_AUTH_TOKEN",
        None,
        description="The authentication (bearer) token OPAL client will use to "
        "authenticate against the policy store (i.e: OPA agent).",
    )
    POLICY_STORE_AUTH_OAUTH_SERVER = confi.str(
        "POLICY_STORE_AUTH_OAUTH_SERVER",
        None,
        description="The authentication server OPAL client will use to authenticate against for retrieving the access_token.",
    )
    POLICY_STORE_AUTH_OAUTH_CLIENT_ID = confi.str(
        "POLICY_STORE_AUTH_OAUTH_CLIENT_ID",
        None,
        description="The client_id OPAL will use to authenticate against the OAuth server.",
    )
    POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET = confi.str(
        "POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET",
        None,
        description="The client secret OPAL will use to authenticate against the OAuth server.",
    )

    POLICY_STORE_CONN_RETRY: ConnRetryOptions = confi.model(
        "POLICY_STORE_CONN_RETRY",
        ConnRetryOptions,
        # defaults are being set according to ConnRetryOptions pydantic definitions (see class)
        {},
        description="Retry options when connecting to the policy store (i.e. the agent that handles the policy, e.g. OPA)",
    )
    POLICY_UPDATER_CONN_RETRY: ConnRetryOptions = confi.model(
        "POLICY_UPDATER_CONN_RETRY",
        ConnRetryOptions,
        {
            "wait_strategy": "random_exponential",
            "max_wait": 10,
            "attempts": 5,
            "wait_time": 1,
        },
        description="Retry options when connecting to the policy source (e.g. the policy bundle server)",
    )

    DATA_STORE_CONN_RETRY: ConnRetryOptions = confi.model(
        "DATA_STORE_CONN_RETRY",
        ConnRetryOptions,
        None,
        description="DEPRECATED - The old confusing name for DATA_UPDATER_CONN_RETRY, kept for backwards compatibility (for now)",
    )

    DATA_UPDATER_CONN_RETRY: ConnRetryOptions = confi.model(
        "DATA_UPDATER_CONN_RETRY",
        ConnRetryOptions,
        {
            "wait_strategy": "random_exponential",
            "max_wait": 10,
            "attempts": 5,
            "wait_time": 1,
        },
        description="Retry options when connecting to the base data source (e.g. an external API server which returns data snapshot)",
    )

    POLICY_STORE_POLICY_PATHS_TO_IGNORE = confi.list(
        "POLICY_STORE_POLICY_PATHS_TO_IGNORE",
        [],
        description="When loading policies manually or otherwise externally into the policy store, use this list of glob patterns to have OPAL ignore and not delete or override them, end paths (without any wildcards in the middle) with '/**' to indicate you want all nested under the path to be ignored",
    )

    POLICY_UPDATER_ENABLED = confi.bool(
        "POLICY_UPDATER_ENABLED",
        True,
        description="If set to False, opal client will not listen to dynamic policy updates."
        "Policy update fetching will be completely disabled.",
    )
    POLICY_STORE_TLS_CLIENT_CERT = confi.str(
        "POLICY_STORE_TLS_CLIENT_CERT",
        None,
        description="Path to the client certificate used for TLS authentication with the policy store",
    )
    POLICY_STORE_TLS_CLIENT_KEY = confi.str(
        "POLICY_STORE_TLS_CLIENT_KEY",
        None,
        description="Path to the client key used for TLS authentication with the policy store",
    )
    POLICY_STORE_TLS_CA = confi.str(
        "POLICY_STORE_TLS_CA",
        None,
        description="Path to the file containing the CA certificate(s) used for TLS authentication with the policy store",
    )

    EXCLUDE_POLICY_STORE_SECRETS = confi.bool(
        "EXCLUDE_POLICY_STORE_SECRETS",
        False,
        description="If set, policy store secrets will be excluded from the /policy-store/config route",
    )

    # create an instance of a policy store upon load
    def load_policy_store():
        from opal_client.policy_store.policy_store_client_factory import (
            PolicyStoreClientFactory,
        )

        return PolicyStoreClientFactory.create()

    # opa runner configuration (OPA can optionally be run by OPAL) ----------------

    # whether or not OPAL should run OPA by itself in the same container
    INLINE_OPA_ENABLED = confi.bool(
        "INLINE_OPA_ENABLED",
        True,
        description="Whether or not OPAL should run OPA by itself in the same container",
    )

    INLINE_OPA_EXEC_PATH = confi.str(
        "INLINE_OPA_EXEC_PATH",
        None,
        description="Path to the OPA executable. Defaults to searching for 'opa' binary in PATH if not specified.",
    )

    # if inline OPA is indeed enabled, user can pass cli options
    # (configuration) that affects how OPA will run
    INLINE_OPA_CONFIG = confi.model(
        "INLINE_OPA_CONFIG",
        OpaServerOptions,
        {},  # defaults are being set according to OpaServerOptions pydantic definitions (see class)
        description="CLI options used when running `opa run --server` inline",
    )

    INLINE_OPA_LOG_FORMAT: EngineLogFormat = confi.enum(
        "INLINE_OPA_LOG_FORMAT",
        EngineLogFormat,
        EngineLogFormat.NONE,
        description="The log format to use for inline OPA logs",
    )

    # Cedar runner configuration (Cedar-engine can optionally be run by OPAL) ----------------

    # whether or not OPAL should run the Cedar agent by itself in the same container
    INLINE_CEDAR_ENABLED = confi.bool(
        "INLINE_CEDAR_ENABLED",
        True,
        description="Whether or not OPAL should run the Cedar agent by itself in the same container",
    )

    INLINE_CEDAR_EXEC_PATH = confi.str(
        "INLINE_CEDAR_EXEC_PATH",
        None,
        description="Path to the Cedar Agent executable. Defaults to searching for 'cedar-agent' binary in PATH if not specified.",
    )

    # if inline Cedar is indeed enabled, user can pass cli options
    # (configuration) that affects how the agent will run
    INLINE_CEDAR_CONFIG = confi.model(
        "INLINE_CEDAR_CONFIG",
        CedarServerOptions,
        {},  # defaults are being set according to CedarServerOptions pydantic definitions (see class)
        description="CLI options used when running the Cedar agent inline",
    )

    INLINE_CEDAR_LOG_FORMAT: EngineLogFormat = confi.enum(
        "INLINE_CEDAR_LOG_FORMAT",
        EngineLogFormat,
        EngineLogFormat.NONE,
        description="The log format to use for inline Cedar logs",
    )

    # configuration for fastapi routes
    ALLOWED_ORIGINS = ["*"]

    # general configuration for pub/sub clients
    KEEP_ALIVE_INTERVAL = confi.int(
        "KEEP_ALIVE_INTERVAL",
        0,
        description="The interval (in seconds) for sending keep-alive messages",
    )

    # Opal Server general configuration -------------------------------------------

    # opal server url
    SERVER_URL = confi.str(
        "SERVER_URL",
        "http://localhost:7002",
        flags=["-s"],
        description="The URL of the OPAL server",
    )
    # opal server pubsub url
    OPAL_WS_ROUTE = "/ws"
    SERVER_WS_URL = confi.str(
        "SERVER_WS_URL",
        confi.delay(
            lambda SERVER_URL="": SERVER_URL.replace("https", "wss").replace(
                "http", "ws"
            )
        ),
        description="The WebSocket URL of the OPAL server",
    )
    SERVER_PUBSUB_URL = confi.str(
        "SERVER_PUBSUB_URL",
        confi.delay("{SERVER_WS_URL}" + f"{OPAL_WS_ROUTE}"),
        description="The Pub/Sub URL of the OPAL server",
    )

    # opal server auth token
    CLIENT_TOKEN = confi.str(
        "CLIENT_TOKEN",
        "THIS_IS_A_DEV_SECRET",
        description="The authentication token for the OPAL server",
        flags=["-t"],
    )

    # client-api server
    CLIENT_API_SERVER_WORKER_COUNT = confi.int(
        "CLIENT_API_SERVER_WORKER_COUNT",
        1,
        description="(if run via CLI) Worker count for the opal-client's internal server",
    )

    CLIENT_API_SERVER_HOST = confi.str(
        "CLIENT_API_SERVER_HOST",
        "127.0.0.1",
        description="(if run via CLI)  Address for the opal-client's internal server to bind",
    )

    CLIENT_API_SERVER_PORT = confi.int(
        "CLIENT_API_SERVER_PORT",
        7000,
        description="(if run via CLI)  Port for the opal-client's internal server to bind",
    )

    WAIT_ON_SERVER_LOAD = confi.bool(
        "WAIT_ON_SERVER_LOAD",
        False,
        description="If set, client would wait for 200 from server's loadlimit endpoint before starting background tasks",
    )

    # Policy updater configuration ------------------------------------------------

    # directories in policy repo we should subscribe to for policy code (rego) modules
    POLICY_SUBSCRIPTION_DIRS = confi.list(
        "POLICY_SUBSCRIPTION_DIRS",
        ["."],
        delimiter=":",
        description="Directories in the policy repo to subscribe to for policy code (rego) modules",
    )

    # Data updater configuration --------------------------------------------------
    DATA_UPDATER_ENABLED = confi.bool(
        "DATA_UPDATER_ENABLED",
        True,
        description="If set to False, opal client will not listen to dynamic data updates. "
        "Dynamic data fetching will be completely disabled.",
    )

    DATA_TOPICS = confi.list(
        "DATA_TOPICS",
        [DEFAULT_DATA_TOPIC],
        description="Data topics to subscribe to",
    )

    DEFAULT_DATA_SOURCES_CONFIG_URL = confi.str(
        "DEFAULT_DATA_SOURCES_CONFIG_URL",
        confi.delay("{SERVER_URL}/data/config"),
        description="Default URL to fetch data configuration from",
    )

    DEFAULT_DATA_URL = confi.str(
        "DEFAULT_DATA_URL",
        "http://localhost:8000/policy-config",
        description="Default URL to fetch data from",
    )

    SHOULD_REPORT_ON_DATA_UPDATES = confi.bool(
        "SHOULD_REPORT_ON_DATA_UPDATES",
        False,
        description="Should the client report on updates to callbacks defined in "
        "DEFAULT_UPDATE_CALLBACKS or within the given updates",
    )
    DEFAULT_UPDATE_CALLBACK_CONFIG = confi.model(
        "DEFAULT_UPDATE_CALLBACK_CONFIG",
        HttpFetcherConfig,
        {
            "method": "post",
            "headers": {"content-type": "application/json"},
            "process_data": False,
        },
        description="Configuration for the default update callback",
    )

    DEFAULT_UPDATE_CALLBACKS = confi.model(
        "DEFAULT_UPDATE_CALLBACKS",
        UpdateCallback,
        confi.delay(
            lambda SERVER_URL="": {"callbacks": [f"{SERVER_URL}/data/callback_report"]}
        ),
        description="Where/How the client should report on the completion of data updates",
    )

    # OPA transaction log / healthcheck policy ------------------------------------
    OPA_HEALTH_CHECK_POLICY_ENABLED = confi.bool(
        "OPA_HEALTH_CHECK_POLICY_ENABLED",
        False,
        description="Should we load a special healthcheck policy into OPA that checks "
        + "that opa was synced correctly and is ready to answer to authorization queries",
    )

    OPA_HEALTH_CHECK_TRANSACTION_LOG_PATH = confi.str(
        "OPA_HEALTH_CHECK_TRANSACTION_LOG_PATH",
        "system/opal/transactions",
        description="Path to OPA document that stores the OPA write transactions",
    )

    OPAL_CLIENT_STAT_ID = confi.str(
        "OPAL_CLIENT_STAT_ID",
        None,
        description="Unique client statistics identifier",
    )

    OPA_HEALTH_CHECK_POLICY_PATH = "engine/healthcheck/opal.rego"

    SCOPE_ID = confi.str("SCOPE_ID", "default", description="OPAL Scope ID")

    STORE_BACKUP_PATH = confi.str(
        "STORE_BACKUP_PATH",
        "/opal/backup/opa.json",
        description="Path to backup policy store's data to",
    )
    STORE_BACKUP_INTERVAL = confi.int(
        "STORE_BACKUP_INTERVAL",
        60,
        description="Interval in seconds to backup policy store's data",
    )
    OFFLINE_MODE_ENABLED = confi.bool(
        "OFFLINE_MODE_ENABLED",
        False,
        description="If set, opal client will try to load policy store from backup file and operate even if server is unreachable. Ignored if INLINE_OPA_ENABLED=False",
    )
    SPLIT_ROOT_DATA = confi.bool(
        "SPLIT_ROOT_DATA", False, description="Split writing data updates to root path"
    )

    def on_load(self):
        # LOGGER
        if self.INLINE_OPA_LOG_FORMAT == EngineLogFormat.NONE:
            opal_common_config.LOG_MODULE_EXCLUDE_LIST.append("opal_client.opa.logger")
            # re-assign to apply to internal confi-entries as well
            opal_common_config.LOG_MODULE_EXCLUDE_LIST = (
                opal_common_config.LOG_MODULE_EXCLUDE_LIST
            )

        if self.DATA_STORE_CONN_RETRY is not None:
            # You should use `DATA_UPDATER_CONN_RETRY`, but that's for backwards compatibility
            self.DATA_UPDATER_CONN_RETRY = self.DATA_STORE_CONN_RETRY


opal_client_config = OpalClientConfig(prefix="OPAL_")
