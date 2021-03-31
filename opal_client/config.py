import os
from enum import Enum

from opal_common.confi import Confi
from opal_common.config import LOG_MODULE_EXCLUDE_LIST
from opal_client.opa.options import OpaServerOptions

confi = Confi(prefix="OPAL_")


# Opal Client general configuration -------------------------------------------
class PolicyStoreTypes(Enum):
    OPA="OPA"
    MOCK="MOCK"

class OpaLogFormat(str, Enum):
    NONE = "none" # no opa logs are piped
    MINIMAL = "minimal" # only the event name is logged
    HTTP = "http" # tries to extract http method, path and response status code
    FULL = "full" # logs the entire data dict returned

# opa client (policy store) configuration
POLICY_STORE_TYPE = confi.enum("POLICY_STORE_TYPE", PolicyStoreTypes, PolicyStoreTypes.OPA)
POLICY_STORE_URL = confi.str("POLICY_STORE_URL", f"http://localhost:8181/v1")

# opa runner configuration (OPA can optionally be run by OPAL) ----------------

# whether or not OPAL should run OPA by itself in the same container
INLINE_OPA_ENABLED = confi.bool("INLINE_OPA_ENABLED", True)

# if inline OPA is indeed enabled, user can pass cli options
# (configuration) that affects how OPA will run
INLINE_OPA_CONFIG = confi.model(
    "INLINE_OPA_CONFIG",
    OpaServerOptions,
    {}, # defaults are being set according to OpaServerOptions pydantic definitions (see class)
    description="cli options used when running `opa run --server` inline"
)

INLINE_OPA_LOG_FORMAT: OpaLogFormat = confi.enum("INLINE_OPA_LOG_FORMAT", OpaLogFormat, OpaLogFormat.NONE)
if INLINE_OPA_LOG_FORMAT == OpaLogFormat.NONE:
    LOG_MODULE_EXCLUDE_LIST.append("opal_client.opa.logger")

# configuration for fastapi routes
ALLOWED_ORIGINS = ["*"]

# general configuration for pub/sub clients
KEEP_ALIVE_INTERVAL = confi.int("KEEP_ALIVE_INTERVAL", 0)


# Opal Server general configuration -------------------------------------------

# opal server url
OPAL_SERVER_URL = confi.str("SERVER_URL", "http://localhost:7002")
_opal_server_ws_url = OPAL_SERVER_URL.replace("https", "ws").replace("http", "ws")

# opal server pubsub url
OPAL_WS_ROUTE = "/ws"
OPAL_SERVER_PUBSUB_URL = f"{_opal_server_ws_url}{OPAL_WS_ROUTE}"

# opal server auth token
CLIENT_TOKEN = confi.str("CLIENT_TOKEN", "THIS_IS_A_DEV_SECRET")

# Policy updater configuration ------------------------------------------------

# directories in policy repo we should subscribe to for policy code (rego) modules
POLICY_SUBSCRIPTION_DIRS = confi.list("POLICY_SUBSCRIPTION_DIRS", ["."], delimiter=":")


# Data updater configuration --------------------------------------------------

# Data topics to subscribe to
DATA_TOPICS = confi.list("DATA_TOPICS", ["policy_data"])

# Default URL to fetch data configuration from
DEFAULT_DATA_SOURCES_CONFIG_URL = confi.str("DEFAULT_DATA_SOURCES_CONFIG_URL", f"{OPAL_SERVER_URL}/data/config")

# Default URL to fetch data from
DEFAULT_DATA_URL = confi.str("DEFAULT_DATA_URL", "http://localhost:8000/policy-config")