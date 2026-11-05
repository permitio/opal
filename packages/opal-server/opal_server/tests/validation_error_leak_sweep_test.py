"""No route may echo a rejected request body back to the caller.

`opal_common.middleware.register_request_validation_exception_handler` strips
the rejected `input` out of 422 responses. That fix was written against the five
routes a review named; this sweeps **every body-accepting route on both the server and the client app**,
discovered from each app's own OpenAPI spec rather than listed by hand, so a
route added later is covered without anyone remembering to add it here.

Why it matters: from pydantic v2 each validation error carries the offending
value, and FastAPI serializes `exc.errors()` wholesale. On a credential-bearing
body that puts a live secret into the 422 - and into every proxy log, APM trace
and error tracker in front of it. It also bypasses `RedactedReprMixin`, because
pydantic-core builds the error from the raw input and never consults the repr.
"""

import json

import pytest
from fastapi.testclient import TestClient
from opal_server.config import opal_server_config

# A value that must never come back. Distinctive enough that a substring match
# cannot be a coincidence.
CANARY = "opal-canary-b6f2c1a9-DO-NOT-ECHO"
CANARY_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\\n" + CANARY + "\\n"

# Keys a credential plausibly arrives under. Each malformed body seeds all of
# them, so a route that echoes ANY part of its input trips the assertion.
SECRET_SHAPED = {
    "Authorization": f"Bearer {CANARY}",
    "private_key": CANARY_KEY,
    "token": CANARY,
    "password": CANARY,
    "api_key": CANARY,
}


def _server_app():
    # scopes routes are gated on this; enable so the sweep sees the full surface
    saved = opal_server_config.SCOPES
    opal_server_config.SCOPES = True
    try:
        from opal_server.server import OpalServer

        return OpalServer(
            init_policy_watcher=False,
            broadcaster_uri=None,
            enable_jwks_endpoint=False,
        ).app
    finally:
        opal_server_config.SCOPES = saved


def _client_app():
    """The opal-CLIENT app.

    Swept too, because `POST /callbacks` lives here and is the one client route
    that accepts a credential-bearing body. It is protected today only because
    the handler is registered in `configure_middleware`, which both apps call -
    i.e. by construction, not by any assertion. Moving that registration into
    the server alone leaves the client echoing whole tokens while every other
    test stays green, which is exactly the regression this covers.
    """
    from opal_client.client import OpalClient

    return OpalClient(
        inline_opa_enabled=False,
        data_updater=False,
        policy_updater=False,
    ).app


APPS = {"server": _server_app(), "client": _client_app()}
CLIENTS = {
    name: TestClient(app, raise_server_exceptions=False) for name, app in APPS.items()
}


def _body_routes():
    """(app, method, path) for every operation declaring a request body."""
    out = []
    for app_name, app in APPS.items():
        for path, ops in app.openapi().get("paths", {}).items():
            for method, op in ops.items():
                if method.upper() in {"POST", "PUT", "PATCH"} and "requestBody" in op:
                    out.append((app_name, method.upper(), path))
    return sorted(out)


BODY_ROUTES = _body_routes()


def _concrete(path: str) -> str:
    """Fill path params with a harmless literal."""
    out = []
    for part in path.split("/"):
        out.append("canary-scope" if part.startswith("{") else part)
    return "/".join(out)


# Malformed bodies, each carrying the canary somewhere. The point is not to be
# valid for any particular route - it is to be REJECTED while containing a
# secret, which is exactly when the echo happened.
MALFORMED_BODIES = {
    "flat_secrets": dict(SECRET_SHAPED),
    "nested_config": {"config": {"headers": dict(SECRET_SHAPED)}},
    "entries_missing_url": {
        "entries": [{"config": {"headers": dict(SECRET_SHAPED)}}],
        "reason": CANARY,
    },
    "bad_auth_discriminator": {
        "policy": {"auth": dict(SECRET_SHAPED, auth_type="not-a-real-type")}
    },
    "wrong_type_for_object": [dict(SECRET_SHAPED)],
    "wrong_type_scalar": CANARY,
}


@pytest.mark.parametrize("app_name,method,path", BODY_ROUTES, ids=lambda v: str(v))
@pytest.mark.parametrize("shape", sorted(MALFORMED_BODIES))
def test_route_never_echoes_the_rejected_body(app_name, method, path, shape):
    response = CLIENTS[app_name].request(
        method, _concrete(path), json=MALFORMED_BODIES[shape]
    )

    body = response.text
    assert CANARY not in body, (
        f"\n[{app_name}] {method} {path} echoed the rejected input back.\n"
        f"  malformed body shape: {shape}\n"
        f"  status: {response.status_code}\n"
        f"  response: {body[:400]}\n\n"
        "A 422 must carry only loc/msg/type - see "
        "opal_common.middleware.register_request_validation_exception_handler."
    )


@pytest.mark.parametrize("app_name,method,path", BODY_ROUTES, ids=lambda v: str(v))
def test_route_still_reports_useful_validation_errors(app_name, method, path):
    """Stripping `input` must not strip the diagnostics with it."""
    response = CLIENTS[app_name].request(
        method, _concrete(path), json=MALFORMED_BODIES["entries_missing_url"]
    )

    if response.status_code != 422:
        pytest.skip(f"[{app_name}] {method} {path} did not reach body validation")

    detail = response.json().get("detail")
    assert (
        isinstance(detail, list) and detail
    ), f"no error detail: {response.text[:200]}"
    for error in detail:
        assert {"loc", "msg", "type"} <= set(error), f"lost diagnostics: {error}"
        for unsafe in ("input", "ctx", "url"):
            assert unsafe not in error, f"{unsafe!r} survived in: {error}"


def test_sweep_found_routes():
    """A sweep over an empty route list would pass for the wrong reason."""
    assert len(BODY_ROUTES) >= 6, (
        f"only {len(BODY_ROUTES)} body-accepting routes discovered - the OpenAPI "
        "sweep is broken and every assertion above is vacuous"
    )


def test_sweep_covers_both_apps():
    """The docstring promises both apps; assert it rather than trusting it.

    The client contributes exactly one body-accepting route, `POST
    /callbacks`, and it is the credential-bearing one. A sweep that
    silently covered only the server would still look healthy on count
    alone.
    """
    apps = {app for app, _, _ in BODY_ROUTES}
    assert apps == {"server", "client"}, f"swept only: {sorted(apps)}"
    assert ("client", "POST", "/callbacks") in BODY_ROUTES, (
        "the client's POST /callbacks is not in the sweep - it is the one client "
        f"route that accepts a credential-bearing body. Found: {BODY_ROUTES}"
    )


def test_canary_would_be_visible_without_the_handler():
    """Control: prove the canary is actually reachable in a 422 body.

    Without this, a canary that never appears even in the unsanitized case
    would make the whole sweep prove nothing.
    """
    from fastapi import FastAPI
    from pydantic import BaseModel

    class _Body(BaseModel):
        required_field: str

    unsanitized = FastAPI()

    @unsanitized.post("/probe")
    async def probe(body: _Body):  # pragma: no cover - never reached on 422
        return {}

    raw = TestClient(unsanitized, raise_server_exceptions=False).post(
        "/probe", json={"config": {"headers": dict(SECRET_SHAPED)}}
    )

    assert raw.status_code == 422
    assert CANARY in raw.text, (
        "the canary does not appear even in an UNSANITIZED 422, so the sweep "
        "above cannot detect a leak"
    )
