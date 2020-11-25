import os

_acalla_backend_url = os.environ.get("AUTHZ_SERVICE_URL", "http://localhost:8000")
POLICY_SERVICE_URL = f"{_acalla_backend_url}/sdk"

_opa_url = os.environ.get("OPA_SERVICE_URL", "http://localhost:8181")
OPA_SERVICE_URL = f"{_opa_url}/v1"

JWT_USER_CLAIMS = [
    "name",
    "given_name",
    "family_name",
    "email",
    "email_verified",
]

UPDATE_INTERVAL_IN_SEC = 5 # 5 seconds