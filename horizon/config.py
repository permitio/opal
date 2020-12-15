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