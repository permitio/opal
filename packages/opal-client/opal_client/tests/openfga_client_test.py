"""Unit and integration tests for OpenFGAClient policy store."""

import asyncio
import contextlib
import io
import json
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import pytest
from aiohttp import web
from opal_client.config import opal_client_config
from opal_client.policy_store.openfga_client import (
    OpenFGAClient,
    build_sdk_write_request,
    normalize_openfga_write_payload,
    parse_fga_dsl_to_json,
)
from opal_client.policy_store.policy_store_client_factory import (
    PolicyStoreClientFactory,
)
from opal_client.policy_store.schemas import PolicyStoreAuth, PolicyStoreTypes
from opal_common.schemas.policy import (
    DataModule,
    DeletedFiles,
    PolicyBundle,
    RegoModule,
)
from opal_common.schemas.store import StoreTransaction, TransactionType
from pydantic import BaseModel

SAMPLE_FGA_DSL = """model
  schema 1.1

type user

type group
  relations
    define member: [user]

type document
  relations
    define owner: [user]
    define editor: [user, group]
    define viewer: [user, group]
"""

SAMPLE_FGA_JSON = json.dumps(
    {
        "schema_version": "1.1",
        "type_definitions": [
            {"type": "user"},
            {
                "type": "document",
                "relations": {
                    "owner": {"this": {}},
                    "viewer": {"this": {}},
                },
            },
        ],
    }
)


class CheckRequestModel(BaseModel):
    user: str
    relation: str
    object: str


def test_parse_fga_dsl_and_json():
    parsed_dsl = parse_fga_dsl_to_json(SAMPLE_FGA_DSL)
    assert parsed_dsl["schema_version"] == "1.1"
    type_names = [t["type"] for t in parsed_dsl["type_definitions"]]
    assert type_names == ["user", "group", "document"]
    assert "owner" in parsed_dsl["type_definitions"][2]["relations"]

    parsed_json = parse_fga_dsl_to_json(SAMPLE_FGA_JSON)
    assert parsed_json["schema_version"] == "1.1"
    assert len(parsed_json["type_definitions"]) == 2

    with pytest.raises(ValueError):
        parse_fga_dsl_to_json("not valid fga dsl")

    with pytest.raises(ValueError):
        parse_fga_dsl_to_json('{"invalid": true}')


def test_normalize_openfga_write_payload():
    tuples = [
        {"user": "user:alice", "relation": "owner", "object": "document:budget"},
    ]
    payload = normalize_openfga_write_payload(tuples, authorization_model_id="m1")
    assert payload == {
        "writes": {"tuple_keys": tuples},
        "authorization_model_id": "m1",
    }

    combined = {
        "writes": [{"user": "user:bob", "relation": "viewer", "object": "document:1"}],
        "deletes": [
            {"user": "user:charlie", "relation": "viewer", "object": "document:1"}
        ],
    }
    payload2 = normalize_openfga_write_payload(combined)
    assert payload2 == {
        "writes": {"tuple_keys": combined["writes"]},
        "deletes": {"tuple_keys": combined["deletes"]},
    }

    assert normalize_openfga_write_payload({}) is None


def test_factory_creates_openfga_client():
    client = PolicyStoreClientFactory.create(
        store_type=PolicyStoreTypes.OPENFGA,
        url="http://localhost:8080",
        save_to_cache=False,
    )
    assert isinstance(client, OpenFGAClient)


def test_openfga_auth_validation_errors():
    with pytest.raises(TypeError):
        OpenFGAClient(
            openfga_server_url="http://localhost:8080",
            openfga_auth_token=None,
            auth_type=PolicyStoreAuth.TOKEN,
        )

    with pytest.raises(TypeError):
        OpenFGAClient(
            openfga_server_url="http://localhost:8080",
            auth_type=PolicyStoreAuth.OAUTH,
            oauth_client_id="only-id",
        )


class _MockSdkClient:
    def __init__(self):
        self.models = []
        self.writes = []

    async def write_authorization_model(self, body):
        self.models.append(body)
        return {"authorization_model_id": "01SDKMODEL"}

    async def write(self, body):
        self.writes.append(body)
        return {}


@pytest.mark.asyncio
async def test_openfga_sdk_client_delegation():
    mock_sdk = _MockSdkClient()
    client = OpenFGAClient(
        openfga_server_url="http://localhost:8080",
        store_id="01STORE",
        sdk_client=mock_sdk,
    )
    assert client.create_sdk_client() is mock_sdk

    res = await client.set_policy("model.fga", SAMPLE_FGA_DSL)
    assert res.status_code == 201
    assert client._authorization_model_id == "01SDKMODEL"
    assert len(mock_sdk.models) == 1

    tuples = [{"user": "user:alice", "relation": "owner", "object": "document:1"}]
    data_res = await client.set_policy_data(tuples)
    assert data_res.status_code == 200
    assert len(mock_sdk.writes) == 1
    assert build_sdk_write_request({"writes": {"tuple_keys": tuples}}) is not None
