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
        description="Specifies the type of policy store to use. Currently supports OPA (Open Policy Agent) and Cedar. This determines how OPAL interacts with the policy engine."
    )
    POLICY_STORE_URL = confi.str(
        "POLICY_STORE_URL",
        "http://localhost:8181",
        description="The URL of the policy store (e.g., OPA server) that OPAL client will interact with. This is where OPAL will push updated policies and data. Ensure this URL is reachable from the OPAL client's network."
    )

    POLICY_STORE_AUTH_TYPE = confi.enum(
        "POLICY_STORE_AUTH_TYPE",
        PolicyStoreAuth,
        PolicyStoreAuth.NONE,
        description="Specifies the authentication method for connecting to the policy store. Possible values are 'none', 'token', 'tls' or 'oauth'. Use this to secure the connection between OPAL and the policy store."
    )
    POLICY_STORE_AUTH_TOKEN = confi.str(
        "POLICY_STORE_AUTH_TOKEN",
        None,
        description="The authentication (bearer) token OPAL client will use to authenticate against the policy store (e.g., OPA). Required if POLICY_STORE_AUTH_TYPE is set to 'token'."
    )
    POLICY_STORE_AUTH_OAUTH_SERVER = confi.str(
        "POLICY_STORE_AUTH_OAUTH_SERVER",
        None,
        description="The OAuth server URL that OPAL client will use to authenticate and retrieve an access token for the policy store. Required if POLICY_STORE_AUTH_TYPE is set to 'oauth'."
    )
    POLICY_STORE_AUTH_OAUTH_CLIENT_ID = confi.str(
        "POLICY_STORE_AUTH_OAUTH_CLIENT_ID",
        None,
        description="The client ID OPAL will use to authenticate against the OAuth server for policy store access. Required if POLICY_STORE_AUTH_TYPE is set to 'oauth'."
    )
    POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET = confi.str(
        "POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET",
        None,
        description="The client secret OPAL will use to authenticate against the OAuth server for policy store access. Required if POLICY_STORE_AUTH_TYPE is set to 'oauth'."
    )

    POLICY_STORE_CONN_RETRY: ConnRetryOptions = confi.model(
        "POLICY_STORE_CONN_RETRY",
        ConnRetryOptions,
        # defaults are being set according to ConnRetryOptions pydantic definitions (see class)
        {},
        description="Retry options when connecting to the policy store (e.g., OPA). Configures how OPAL handles connection failures, including wait times and retry attempts."
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
        description="Retry options when connecting to the policy source (e.g., the policy bundle server). Configures how OPAL handles connection failures when fetching policy updates."
    )

    DATA_STORE_CONN_RETRY: ConnRetryOptions = confi.model(
        "DATA_STORE_CONN_RETRY",
        ConnRetryOptions,
        None,
        description="DEPRECATED - The old confusing name for DATA_UPDATER_CONN_RETRY, kept for backwards compatibility (for now). Use DATA_UPDATER_CONN_RETRY instead."
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
        description="Retry options when connecting to the base data source (e.g., an external API server which returns data snapshots). Configures how OPAL handles connection failures when fetching data updates."
    )

    POLICY_STORE_POLICY_PATHS_TO_IGNORE = confi.list(
        "POLICY_STORE_POLICY_PATHS_TO_IGNORE",
        [],
        description="A list of glob-style paths or paths ending with '/**' to indicate policy paths that should be ignored by OPAL. Use this to prevent OPAL from overwriting or deleting specific policies in the policy store."
    )

    POLICY_UPDATER_ENABLED = confi.bool(
        "POLICY_UPDATER_ENABLED",
        True,
        "Policy update fetching will be completely disabled.",
        description="Controls whether OPAL client listens to dynamic policy updates. If set to False, policy update fetching will be completely disabled, and OPAL will not fetch policies or listen to policy updates."
    )
    POLICY_STORE_TLS_CLIENT_CERT = confi.str(
        "POLICY_STORE_TLS_CLIENT_CERT",
        None,
        description="Path to the client certificate file used for TLS authentication with the policy store. Use this for secure communication between OPAL and the policy store."
    )
    POLICY_STORE_TLS_CLIENT_KEY = confi.str(
        "POLICY_STORE_TLS_CLIENT_KEY",
        None,
        description="Path to the client key file used for TLS authentication with the policy store. Paired with POLICY_STORE_TLS_CLIENT_CERT for secure communication."
    )
    POLICY_STORE_TLS_CA = confi.str(
        "POLICY_STORE_TLS_CA",
        None,
        description="Path to the file containing the CA certificate(s) used for TLS authentication with the policy store. Use this to verify the policy store's certificate."
    )

    EXCLUDE_POLICY_STORE_SECRETS = confi.bool(
        "EXCLUDE_POLICY_STORE_SECRETS",
        False,
        description="If set to True, policy store secrets will be excluded from the /policy-store/config route. Use this to enhance security by not exposing sensitive information."
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
        description="Determines whether OPAL should run OPA inline within its own container. When enabled, OPAL manages OPA directly, simplifying deployment but potentially limiting OPA configuration options."
    )

    # if inline OPA is indeed enabled, user can pass cli options
    # (configuration) that affects how OPA will run
    INLINE_OPA_CONFIG = confi.model(
        "INLINE_OPA_CONFIG",
        OpaServerOptions,
        {}, # defaults are being set according to OpaServerOptions pydantic definitions (see class)
        description="CLI options used when running `opa run --server` inline. This allows you to configure how OPA runs when managed by OPAL, including server configuration options that affect OPA's behavior."
    )

    INLINE_OPA_LOG_FORMAT: EngineLogFormat = confi.enum(
        "INLINE_OPA_LOG_FORMAT",
        EngineLogFormat,
        EngineLogFormat.NONE,
        description="Specifies the log format for inline OPA. Options are: none (no OPA logs), minimal (only event names), http (HTTP method, path, and status code), or full (entire data dict). Use this to control the verbosity of OPA logs when run inline."
    )

    # Cedar runner configuration (Cedar-engine can optionally be run by OPAL) ----------------

    INLINE_CEDAR_ENABLED = confi.bool(
        "INLINE_CEDAR_ENABLED",
        True,
        description="Determines whether OPAL should run the Cedar agent inline within its own container. Similar to INLINE_OPA_ENABLED, but for Cedar policy engine."
    )

    INLINE_CEDAR_CONFIG = confi.model(
        "INLINE_CEDAR_CONFIG",
        CedarServerOptions,
        {}, # defaults are being set according to CedarServerOptions pydantic definitions (see class)
        description="CLI options used when running the Cedar agent inline. This allows you to configure how the Cedar agent runs when managed by OPAL."
    )

    INLINE_CEDAR_LOG_FORMAT: EngineLogFormat = confi.enum(
        "INLINE_CEDAR_LOG_FORMAT",
        EngineLogFormat,
        EngineLogFormat.NONE,
        description="Specifies the log format for inline Cedar. Options are the same as INLINE_OPA_LOG_FORMAT. Use this to control the verbosity of Cedar logs when run inline."
    )

    # configuration for fastapi routes
    ALLOWED_ORIGINS = ["*"]

    # general configuration for pub/sub clients
    KEEP_ALIVE_INTERVAL = confi.int(
        "KEEP_ALIVE_INTERVAL",
        0,
        description="Interval in seconds for sending keep-alive messages on the WebSocket connection to the OPAL server. Set to 0 to disable. Use this to maintain long-lived connections in environments with aggressive timeouts."
    )

    # Opal Server general configuration -------------------------------------------

    # opal server url
    SERVER_URL = confi.str(
        "SERVER_URL",
        "http://localhost:7002",
        description="The URL of the OPAL server that this client will connect to for receiving policy and data updates. Ensure this URL is reachable from the client's network.",
        flags=["-s"]
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
        description="WebSocket URL of the OPAL server, automatically derived from SERVER_URL. This is used for real-time communication between the OPAL client and server."
    )
    SERVER_PUBSUB_URL = confi.str(
        "SERVER_PUBSUB_URL",
        confi.delay("{SERVER_WS_URL}" + f"{OPAL_WS_ROUTE}"),
        description="PubSub URL of the OPAL server, used for subscribing to real-time updates. This is typically the WebSocket URL with the /ws route appended."
    )

    # opal server auth token
    CLIENT_TOKEN = confi.str(
        "CLIENT_TOKEN",
        "THIS_IS_A_DEV_SECRET",
        description="Authentication token used by the OPAL client to authenticate with the OPAL server. Ensure this matches the token configured on the server side for secure communication.",
        flags=["-t"]
    )

    # client-api server
    CLIENT_API_SERVER_WORKER_COUNT = confi.int(
        "CLIENT_API_SERVER_WORKER_COUNT",
        1,
        description="Number of worker processes for the OPAL client's internal server when run via CLI. Adjust based on expected load and available resources."
    )

    CLIENT_API_SERVER_HOST = confi.str(
        "CLIENT_API_SERVER_HOST",
        "127.0.0.1",
        description="Address for the OPAL client's internal server to bind to when run via CLI. Use '0.0.0.0' to allow external connections, or '127.0.0.1' for local-only access."
    )

    CLIENT_API_SERVER_PORT = confi.int(
        "CLIENT_API_SERVER_PORT",
        7000,
        description="Port for the OPAL client's internal server to bind to when run via CLI. Ensure this port is available and not blocked by firewalls."
    )

    WAIT_ON_SERVER_LOAD = confi.bool(
        "WAIT_ON_SERVER_LOAD",
        False,
        description="If set to True, the OPAL client will wait for a 200 response from the server's loadlimit endpoint before starting background tasks. This ensures the server is ready to handle requests."
    )

    # Policy updater configuration ------------------------------------------------

    # directories in policy repo we should subscribe to for policy code (rego) modules
    POLICY_SUBSCRIPTION_DIRS = confi.list(
        "POLICY_SUBSCRIPTION_DIRS",
        ["."],
        delimiter=":",
        description="Colon-separated list of directories in the policy repository to subscribe to for policy updates. Use '.' for the root directory. This allows fine-grained control over which policies the client receives."
    )

    # Data updater configuration --------------------------------------------------
    DATA_UPDATER_ENABLED = confi.bool(
        "DATA_UPDATER_ENABLED",
        True,
        description="Controls whether the OPAL client listens to dynamic data updates. If set to False, dynamic data fetching will be completely disabled, and OPAL will not process data updates."
    )

    DATA_TOPICS = confi.list(
        "DATA_TOPICS",
        [DEFAULT_DATA_TOPIC],
        description="List of data topics to subscribe to for updates. Use this to filter which data updates the client receives, allowing for more targeted data distribution."
    )

    DEFAULT_DATA_SOURCES_CONFIG_URL = confi.str(
        "DEFAULT_DATA_SOURCES_CONFIG_URL",
        confi.delay("{SERVER_URL}/data/config"),
        description="URL to fetch the initial data sources configuration. This configuration tells the OPAL client where to fetch data from and how to structure it in the policy store."
    )

    DEFAULT_DATA_URL = confi.str(
        "DEFAULT_DATA_URL",
        "http://localhost:8000/policy-config",
        description="Default URL to fetch policy data from if not specified in the data sources configuration. This serves as a fallback for data fetching."
    )

    SHOULD_REPORT_ON_DATA_UPDATES = confi.bool(
        "SHOULD_REPORT_ON_DATA_UPDATES",
        False,
        description="If set to True, the client will report on data updates to callbacks defined in DEFAULT_UPDATE_CALLBACKS or within the given updates. This can be used for monitoring or triggering actions based on data changes."
    )
    DEFAULT_UPDATE_CALLBACK_CONFIG = confi.model(
        "DEFAULT_UPDATE_CALLBACK_CONFIG",
        HttpFetcherConfig,
        {
            "method": "post",
            "headers": {"content-type": "application/json"},
            "process_data": False,
        },
        description="Default configuration for update callbacks, including HTTP method, headers, and data processing options. This defines how the client reports on data updates when SHOULD_REPORT_ON_DATA_UPDATES is True."
    )

    DEFAULT_UPDATE_CALLBACKS = confi.model(
        "DEFAULT_UPDATE_CALLBACKS",
        UpdateCallback,
        confi.delay(
            lambda SERVER_URL="": {"callbacks": [f"{SERVER_URL}/data/callback_report"]}
        ),
        description="Specifies where and how the client should report on the completion of data updates. By default, it reports to the OPAL server's callback endpoint."
    )

    # OPA transaction log / healthcheck policy ------------------------------------
    OPA_HEALTH_CHECK_POLICY_ENABLED = confi.bool(
        "OPA_HEALTH_CHECK_POLICY_ENABLED",
        False,
        description="When enabled, OPAL loads a special healthcheck policy into OPA that verifies OPA was synced correctly and is ready to answer authorization queries. This helps ensure the integrity of the policy store."
    )

    OPA_HEALTH_CHECK_TRANSACTION_LOG_PATH = confi.str(
        "OPA_HEALTH_CHECK_TRANSACTION_LOG_PATH",
        "system/opal/transactions",
        description="Path to the OPA document that stores the OPA write transactions for health checking. This is used in conjunction with the healthcheck policy when OPA_HEALTH_CHECK_POLICY_ENABLED is True."
    )

    OPAL_CLIENT_STAT_ID = confi.str(
        "OPAL_CLIENT_STAT_ID",
        None,
        description="Unique identifier for client statistics. This can be used to track and differentiate between multiple OPAL clients in a distributed setup."
    )

    OPA_HEALTH_CHECK_POLICY_PATH = "engine/healthcheck/opal.rego"

    SCOPE_ID = confi.str(
        "SCOPE_ID",
        "default",
        description="Identifier for the OPAL scope. This can be used to logically separate different OPAL deployments or environments within the same infrastructure."
    )

    STORE_BACKUP_PATH = confi.str(
        "STORE_BACKUP_PATH",
        "/opal/backup/opa.json",
        description="Path to backup the policy store's data. This is used for persistence and recovery in case of restarts or failures."
    )
    STORE_BACKUP_INTERVAL = confi.int(
        "STORE_BACKUP_INTERVAL",
        60,
        description="Interval in seconds to backup the policy store's data. Regular backups ensure data persistence and allow for quicker recovery."
    )
    OFFLINE_MODE_ENABLED = confi.bool(
        "OFFLINE_MODE_ENABLED",
        False,
        description="When enabled, the OPAL client will attempt to load the policy store from a backup file and operate even if the OPAL server is unreachable. This is ignored if INLINE_OPA_ENABLED is False. Useful for scenarios where temporary network issues shouldn't impact policy enforcement."
    )
    SPLIT_ROOT_DATA = confi.bool(
        "SPLIT_ROOT_DATA", 
        False, 
        description="When enabled, OPAL will split writing data updates to the root path. This can be useful for managing large datasets or improving update performance in certain scenarios."
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