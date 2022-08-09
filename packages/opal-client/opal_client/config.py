from enum import Enum

from opal_client.opa.options import OpaServerOptions
from opal_client.policy_store.options import PolicyStoreConnRetryOptions
from opal_client.policy_store.schemas import PolicyStoreTypes
from opal_common.confi import Confi, confi
from opal_common.config import opal_common_config
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.schemas.data import UpdateCallback


# Opal Client general configuration -------------------------------------------
class OpaLogFormat(str, Enum):
    NONE = "none"  # no opa logs are piped
    MINIMAL = "minimal"  # only the event name is logged
    HTTP = "http"  # tries to extract http method, path and response status code
    FULL = "full"  # logs the entire data dict returned


class OpalClientConfig(Confi):
    # opa client (policy store) configuration
    POLICY_STORE_TYPE = confi.enum(
        "POLICY_STORE_TYPE", PolicyStoreTypes, PolicyStoreTypes.OPA
    )
    POLICY_STORE_URL = confi.str("POLICY_STORE_URL", f"http://localhost:8181")
    POLICY_STORE_AUTH_TOKEN = confi.str(
        "POLICY_STORE_AUTH_TOKEN",
        None,
        description="the authentication (bearer) token OPAL client will use to authenticate against the policy store (i.e: OPA agent)",
    )
    POLICY_STORE_CONN_RETRY = confi.model(
        "POLICY_STORE_CONN_RETRY",
        PolicyStoreConnRetryOptions,
        {},  # defaults are being set according to PolicyStoreConnRetryOptions pydantic definitions (see class)
        description="retry options when connecting to the policy store",
    )
    # create an instance of a policy store upon load

    def load_policy_store():
        from opal_client.policy_store.policy_store_client_factory import (
            PolicyStoreClientFactory,
        )

        return PolicyStoreClientFactory.create()

    # opa runner configuration (OPA can optionally be run by OPAL) ----------------

    # whether or not OPAL should run OPA by itself in the same container
    INLINE_OPA_ENABLED = confi.bool("INLINE_OPA_ENABLED", True)

    # if inline OPA is indeed enabled, user can pass cli options
    # (configuration) that affects how OPA will run
    INLINE_OPA_CONFIG = confi.model(
        "INLINE_OPA_CONFIG",
        OpaServerOptions,
        {},  # defaults are being set according to OpaServerOptions pydantic definitions (see class)
        description="cli options used when running `opa run --server` inline",
    )

    INLINE_OPA_LOG_FORMAT: OpaLogFormat = confi.enum(
        "INLINE_OPA_LOG_FORMAT", OpaLogFormat, OpaLogFormat.NONE
    )

    # configuration for fastapi routes
    ALLOWED_ORIGINS = ["*"]

    # general configuration for pub/sub clients
    KEEP_ALIVE_INTERVAL = confi.int("KEEP_ALIVE_INTERVAL", 0)

    # Opal Server general configuration -------------------------------------------

    # opal server url
    SERVER_URL = confi.str("SERVER_URL", "http://localhost:7002", flags=["-s"])
    # opal server pubsub url
    OPAL_WS_ROUTE = "/ws"
    SERVER_WS_URL = confi.str(
        "SERVER_WS_URL",
        confi.delay(
            lambda SERVER_URL="": SERVER_URL.replace("https", "wss").replace(
                "http", "ws"
            )
        ),
    )
    SERVER_PUBSUB_URL = confi.str(
        "SERVER_PUBSUB_URL", confi.delay("{SERVER_WS_URL}" + f"{OPAL_WS_ROUTE}")
    )

    # opal server auth token
    CLIENT_TOKEN = confi.str(
        "CLIENT_TOKEN",
        "THIS_IS_A_DEV_SECRET",
        description="opal server auth token",
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
        description="directories in policy repo we should subscribe to",
    )

    # Data updater configuration --------------------------------------------------
    DATA_UPDATER_ENABLED = confi.bool(
        "DATA_UPDATER_ENABLED",
        True,
        description="If set to False, opal client will not listen to dynamic data updates. Dynamic data fetching will be completely disabled.",
    )

    DATA_TOPICS = confi.list(
        "DATA_TOPICS", ["policy_data"], description="Data topics to subscribe to"
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
        description="Should the client report on updates to callbacks defined in DEFAULT_UPDATE_CALLBACKS or within the given updates",
    )
    DEFAULT_UPDATE_CALLBACK_CONFIG = confi.model(
        "DEFAULT_UPDATE_CALLBACK_CONFIG",
        HttpFetcherConfig,
        {
            "method": "post",
            "headers": {"content-type": "application/json"},
            "process_data": False,
        },
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
        "OPAL_CLIENT_STAT_ID", None, description="Unique client statistics identifier"
    )

    OPA_HEALTH_CHECK_POLICY_PATH = "opa/healthcheck/opal.rego"

    SCOPE_ID = confi.str("SCOPE_ID", "default", description="OPAL Scope ID")

    def on_load(self):
        # LOGGER
        if self.INLINE_OPA_LOG_FORMAT == OpaLogFormat.NONE:
            opal_common_config.LOG_MODULE_EXCLUDE_LIST.append("opal_client.opa.logger")
            # re-assign to apply to internal confi-entries as well
            opal_common_config.LOG_MODULE_EXCLUDE_LIST = (
                opal_common_config.LOG_MODULE_EXCLUDE_LIST
            )


opal_client_config = OpalClientConfig(prefix="OPAL_")
