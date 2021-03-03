import os
from enum import Enum

from opal.common.confi import Confi

config = Confi()

class PolicyStoreTypes(Enum):
    OPA="OPA"
    MOCK="MOCK"
        
# Data topics to subscribe to
DATA_TOPICS = config.list("DATA_TOPICS", ["policy_data"])
DEFAULT_DATA_URL = config.str("DEFAULT_DATA_URL", "http://localhost:8000/policy-config")


# backend service
BACKEND_URL = config.str("OPAL_SERVER_URL", "http://localhost:8000")
BACKEND_SERVICE_LEGACY_URL = f"{BACKEND_URL}/sdk"
BACKEND_SERVICE_URL = f"{BACKEND_URL}/v1"

# data service (currently points to backend)
_ws_backend_url = BACKEND_URL.replace("https", "ws").replace("http", "ws")
DATA_UPDATES_ROUTE = "/sdk/ws"
DATA_UPDATES_WS_URL = f"{_ws_backend_url}{DATA_UPDATES_ROUTE}"

# policy service (opal server)
POLICY_SERVICE_URL = config.str("POLICY_SERVICE_URL", "http://localhost:7002")
_policy_ws_url = POLICY_SERVICE_URL.replace("https", "ws").replace("http", "ws")
POLICY_UPDATES_WS_URL = f"{_policy_ws_url}/ws"

POLICY_SUBSCRIPTION_DIRS = config.list("POLICY_SUBSCRIPTION_DIRS", ["some/dir","other"], delimiter=":")

POLICY_STORE_TYPE = config.enum("POLICY_STORE_TYPE", PolicyStoreTypes, PolicyStoreTypes.OPA)

OPA_PORT = config.str("OPA_PORT", "8181")
_opa_url = config.str("OPA_SERVICE_URL", f"http://localhost:{OPA_PORT}")
POLICY_STORE_URL = f"{_opa_url}/v1"

CLIENT_TOKEN = config.str("CLIENT_TOKEN", "PJUKkuwiJkKxbIoC4o4cguWxB_2gX6MyATYKc2OCM")

ALLOWED_ORIGINS = ["*"]


KEEP_ALIVE_INTERVAL = config.int("AUTHZ_KEEP_ALIVE", 0)


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