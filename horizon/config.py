import os

_acalla_backend_url = os.environ.get("AUTHZ_SERVICE_URL", "http://localhost:8000")
POLICY_SERVICE_URL = f"{_acalla_backend_url}/sdk"

_ws_backend_url = _acalla_backend_url.replace("https", "ws").replace("http", "ws")
POLICY_UPDATES_WS_URL = f"{_ws_backend_url}/sdk/ws"

OPA_PORT = os.environ.get("OPA_PORT", "8181")
_opa_url = os.environ.get("OPA_SERVICE_URL", f"http://localhost:{OPA_PORT}")
OPA_SERVICE_URL = f"{_opa_url}/v1"

CLIENT_TOKEN = os.environ.get("CLIENT_TOKEN", "PJUKkuwiJkKxbIoC4o4cguWxB_2gX6MyATYKc2OCM")

ALLOWED_ORIGINS = ["*"]

try:
    KEEP_ALIVE_INTERVAL = int(os.environ.get("AUTHZ_KEEP_ALIVE", "0"))
except ValueError:
    KEEP_ALIVE_INTERVAL = 0

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