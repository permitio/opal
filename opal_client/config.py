from sys import prefix
import opal_client
import os
from enum import Enum

from opal_common.confi import Confi, confi
from opal_common.config import opal_common_config
from opal_client.opa.options import OpaServerOptions


# Opal Client general configuration -------------------------------------------
class PolicyStoreTypes(Enum):
    OPA = "OPA"
    MOCK = "MOCK"


class OpaLogFormat(str, Enum):
    NONE = "none"  # no opa logs are piped
    MINIMAL = "minimal"  # only the event name is logged
    HTTP = "http"  # tries to extract http method, path and response status code
    FULL = "full"  # logs the entire data dict returned


class OpalClientConfig(Confi):
    # opa client (policy store) configuration
    POLICY_STORE_TYPE = confi.enum("POLICY_STORE_TYPE", PolicyStoreTypes, PolicyStoreTypes.OPA)
    POLICY_STORE_URL = confi.str("POLICY_STORE_URL", f"http://localhost:8181/v1")
    # create an instance of a policy store upon load
    def load_policy_store():
        from opal_client.policy_store import PolicyStoreClientFactory
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
        description="cli options used when running `opa run --server` inline"
    )

    INLINE_OPA_LOG_FORMAT: OpaLogFormat = confi.enum("INLINE_OPA_LOG_FORMAT", OpaLogFormat, OpaLogFormat.NONE)

    # configuration for fastapi routes
    ALLOWED_ORIGINS = ["*"]

    # general configuration for pub/sub clients
    KEEP_ALIVE_INTERVAL = confi.int("KEEP_ALIVE_INTERVAL", 0)

    # Opal Server general configuration -------------------------------------------

    # opal server url
    SERVER_URL = confi.str("SERVER_URL", "http://localhost:7002", flags=["-s"])
    # opal server pubsub url
    OPAL_WS_ROUTE = "/ws"
    SERVER_WS_URL = confi.str("SERVER_WS_URL", confi.delay(lambda SERVER_URL="":SERVER_URL.replace("https", "wss").replace("http", "ws")))
    SERVER_PUBSUB_URL = confi.str("SERVER_PUBSUB_URL", confi.delay("{SERVER_WS_URL}" + f"{OPAL_WS_ROUTE}")) 

    # opal server auth token
    CLIENT_TOKEN = confi.str("CLIENT_TOKEN", "THIS_IS_A_DEV_SECRET",
                             description="opal server auth token", flags=["-t"])

    # client-api server
    CLIENT_API_SERVER_WORKER_COUNT = confi.int("CLIENT_API_SERVER_WORKER_COUNT", 1,
                                               description="(if run via CLI) Worker count for the opal-client's internal server")

    CLIENT_API_SERVER_HOST = confi.str("CLIENT_API_SERVER_HOST", "127.0.0.1",
                                       description="(if run via CLI)  Address for the opal-client's internal server to bind")

    CLIENT_API_SERVER_PORT = confi.int("CLIENT_API_SERVER_PORT", 7000,
                                       description="(if run via CLI)  Port for the opal-client's internal server to bind")

    # Policy updater configuration ------------------------------------------------

    # directories in policy repo we should subscribe to for policy code (rego) modules
    POLICY_SUBSCRIPTION_DIRS = confi.list("POLICY_SUBSCRIPTION_DIRS", ["."], delimiter=":",
                                          description="directories in policy repo we should subscribe to")

    # Data updater configuration --------------------------------------------------
    DATA_TOPICS = confi.list("DATA_TOPICS", ["policy_data"],
                             description="Data topics to subscribe to")

    DEFAULT_DATA_SOURCES_CONFIG_URL = confi.str("DEFAULT_DATA_SOURCES_CONFIG_URL", confi.delay("{SERVER_URL}/data/config"),
                                                description="Default URL to fetch data configuration from")

    DEFAULT_DATA_URL = confi.str("DEFAULT_DATA_URL", "http://localhost:8000/policy-config",
                                 description="Default URL to fetch data from")

    def on_load(self):
        # LOGGER
        if self.INLINE_OPA_LOG_FORMAT == OpaLogFormat.NONE:
            opal_common_config.LOG_MODULE_EXCLUDE_LIST.append("opal_client.opa.logger")
            # re-assign to apply to internal confi-entries as well
            opal_common_config.LOG_MODULE_EXCLUDE_LIST = opal_common_config.LOG_MODULE_EXCLUDE_LIST


opal_client_config = OpalClientConfig(prefix="OPAL_")
