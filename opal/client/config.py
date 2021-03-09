import os
from enum import Enum

from opal.common.confi import Confi

confi = Confi()


# Opal Client general configuration -------------------------------------------
class PolicyStoreTypes(Enum):
    OPA="OPA"
    MOCK="MOCK"

# opa client (policy store) configuration
POLICY_STORE_TYPE = confi.enum("POLICY_STORE_TYPE", PolicyStoreTypes, PolicyStoreTypes.OPA)
OPA_PORT = confi.str("OPA_PORT", "8181")
_opa_url = confi.str("OPA_SERVICE_URL", f"http://localhost:{OPA_PORT}")
POLICY_STORE_URL = f"{_opa_url}/v1"

# configuration for fastapi routes
ALLOWED_ORIGINS = ["*"]

# general configuration for pub/sub clients
KEEP_ALIVE_INTERVAL = confi.int("AUTHZ_KEEP_ALIVE", 0)


# Opal Server general configuration -------------------------------------------

# opal server url
OPAL_SERVER_URL = confi.str("OPAL_SERVER_URL", "http://localhost:7002")
_opal_server_ws_url = OPAL_SERVER_URL.replace("https", "ws").replace("http", "ws")

# opal server ws pubsub url
OPAL_WS_ROUTE = "/ws"
OPAL_SERVER_WS_URL = f"{_opal_server_ws_url}{OPAL_WS_ROUTE}"

# opal server auth token
CLIENT_TOKEN = confi.str("CLIENT_TOKEN", "THIS_IS_A_DEV_SECRET")

# Policy updater configuration ------------------------------------------------

# directories in policy repo we should subscribe to for policy code (rego) modules
POLICY_SUBSCRIPTION_DIRS = confi.list("POLICY_SUBSCRIPTION_DIRS", ["some/dir","other"], delimiter=":")


# Data updater configuration --------------------------------------------------

# Data topics to subscribe to
DATA_TOPICS = confi.list("DATA_TOPICS", ["policy_data"])

# Default URL to fetch data configuration from
DEFAULT_DATA_SOURCES_CONFIG_URL = confi.str("DEFAULT_DATA_SOURCES_CONFIG_URL", f"{OPAL_SERVER_URL}/data/config")

# Default URL to fetch data from
DEFAULT_DATA_URL = confi.str("DEFAULT_DATA_URL", "http://localhost:8000/policy-config")


# Authorizon Sidecar configuration --------------------------------------------

# backend service
BACKEND_URL = confi.str("AUTHORIZON_API_URL", "http://localhost:8000")
BACKEND_SERVICE_LEGACY_URL = f"{BACKEND_URL}/sdk"
BACKEND_SERVICE_URL = f"{BACKEND_URL}/v1"

OPENAPI_TAGS_METADATA = [
    {
        "name": "Authorization API",
        "description": "Authorization queries to OPA. These queries are answered locally by OPA " + \
            "and do not require the cloud service. Latency should be very low (< 20ms per query)"
    },
    {
        "name": "Local Queries",
        "description": "These queries are done locally against the sidecar and do not " + \
            "involve a network round-trip to Authorizon cloud API. Therefore they are safe " + \
            "to use with reasonable performance (i.e: with negligible latency) in the context of a user request.",
    },
    {
        "name": "Policy Updater",
        "description": "API to manually trigger and control the local policy caching and refetching."
    },
    {
        "name": "Cloud API Proxy",
        "description": "These endpoints proxy the Authorizon cloud api, and therefore **incur high-latency**. " + \
            "You should not use the cloud API in the standard request flow of users, i.e in places where the incurred " + \
            "added latency will affect your entire api. A good place to call the cloud API will be in one-time user events " + \
            "such as user registration (i.e: calling sync user, assigning initial user roles, etc.). " + \
            "The sidecar will proxy to the cloud every request prefixed with '/sdk'.",
        "externalDocs": {
            "description": "The cloud api complete docs are located here:",
            "url": "https://api.authorizon.com/redoc",
        },
    }
]