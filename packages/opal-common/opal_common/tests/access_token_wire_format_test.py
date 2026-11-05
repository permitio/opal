"""``AccessTokenRequest.ttl`` must stay on the wire as float seconds.

pydantic v2 serializes a ``timedelta`` as an ISO-8601 duration and collapses 365
days - the CLI default - to ``"P1Y"``, which a pydantic v1 duration parser
cannot read. Without a numeric wire format, ``opal-client obtain-token`` from an
upgraded CLI 422s against a server that has not restarted yet.
"""

import json
from datetime import timedelta

import pytest
from opal_common.schemas.security import AccessTokenRequest, PeerType


@pytest.mark.parametrize(
    "ttl",
    [
        timedelta(days=365),  # the CLI default, and the OpenAPI default
        timedelta(days=366),
        timedelta(days=364),
        timedelta(days=730),
        timedelta(seconds=60),
    ],
)
def test_ttl_serializes_as_a_number(ttl):
    body = json.loads(AccessTokenRequest(type="client", ttl=ttl).model_dump_json())

    assert isinstance(body["ttl"], (int, float))
    assert not isinstance(body["ttl"], bool)
    assert body["ttl"] == ttl.total_seconds()


def test_default_ttl_is_a_year_in_seconds():
    body = json.loads(AccessTokenRequest(type="client").model_dump_json())

    assert body["ttl"] == 31536000.0


def test_ttl_never_serializes_an_iso_duration():
    """``P1Y`` is the specific value a v1 server cannot parse."""
    for days in (1, 30, 364, 365, 366, 730, 1095):
        body = json.loads(
            AccessTokenRequest(
                type="client", ttl=timedelta(days=days)
            ).model_dump_json()
        )
        assert not isinstance(body["ttl"], str), f"{days}d serialized as a duration"


def test_openapi_default_is_numeric():
    """A codegen'd client reads the default straight out of the schema."""
    schema = AccessTokenRequest.model_json_schema()

    assert schema["properties"]["ttl"]["default"] == 31536000.0


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_openapi_types_ttl_as_its_wire_form(mode):
    """Pydantic 2.14 types a timedelta's input schema as an ISO-8601 string.

    That is the validation-mode schema, which FastAPI publishes for the
    ``/token`` request body. A client generated from it would send
    ``"P1Y"``, the value a v1 server cannot parse; the schema must say
    number, as the wire does. The validation case reproduces the 2.14 bug.
    The serialization case passes on 2.14 without the fix too: it is a
    regression guard for the response schema, which ``ser_json_timedelta``
    keeps numeric today.
    """
    ttl = AccessTokenRequest.model_json_schema(mode=mode)["properties"]["ttl"]

    assert ttl["type"] == "number"
    assert "format" not in ttl
    assert ttl["default"] == 31536000.0


@pytest.mark.parametrize("wire_ttl", [31536000.0, 31536000, 60.5])
def test_numeric_wire_form_still_round_trips(wire_ttl):
    """The reverse direction - old client to new server - must keep working."""
    request = AccessTokenRequest.model_validate_json(
        json.dumps({"type": "client", "ttl": wire_ttl, "claims": {}})
    )

    assert request.ttl == timedelta(seconds=wire_ttl)
    assert request.type == PeerType.client
