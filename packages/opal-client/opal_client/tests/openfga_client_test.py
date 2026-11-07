import json
from typing import Any, Dict

import pytest
from opal_client.policy_store.openfga_client import (
    OpenFGAClient,
    normalize_openfga_write_payload,
    parse_fga_dsl_to_json,
)
from opal_client.policy_store.openfga_tuples import (
    extract_read_tuples,
    filter_tuples_by_path,
)
from opal_client.policy_store.policy_store_client_factory import (
    PolicyStoreClientFactory,
)
from opal_client.policy_store.schemas import PolicyStoreAuth, PolicyStoreTypes
from opal_common.schemas.store import StoreTransaction, TransactionType
from pydantic import BaseModel

SAMPLE_FGA_DSL = """model
  schema 1.1

type user

type organization
  relations
    define member: [user]
    define admin: [user]

type document
  relations
    define org: [organization]
    define owner: [user] or admin from org
    define editor: [user, organization#member] or owner
    define viewer: [user, user:*] and editor but not owner
"""


class CheckQueryInput(BaseModel):
    user: str
    relation: str
    object: str


class ExpandQueryInput(BaseModel):
    relation: str
    object: str


def test_parse_fga_dsl_and_json():
    parsed_dsl = parse_fga_dsl_to_json(SAMPLE_FGA_DSL)
    assert parsed_dsl["schema_version"] == "1.1"
    type_names = [t["type"] for t in parsed_dsl["type_definitions"]]
    assert type_names == ["user", "organization", "document"]
    doc_rels = parsed_dsl["type_definitions"][2]["relations"]
    assert "union" in doc_rels["owner"]
    assert "difference" in doc_rels["viewer"]

    raw_json = json.dumps(parsed_dsl)
    assert parse_fga_dsl_to_json(raw_json)["schema_version"] == "1.1"


def test_parse_fga_dsl_invalid_inputs():
    with pytest.raises(ValueError):
        parse_fga_dsl_to_json("invalid dsl without schema")

    with pytest.raises(ValueError):
        parse_fga_dsl_to_json("{\"missing_types\": true}")


def test_tuple_normalization_and_path_filtering():
    tuples = [
        {"user": "user:alice", "relation": "owner", "object": "document:roadmap"},
        {"user": "user:bob", "relation": "viewer", "object": "folder:eng"},
    ]
    payload = normalize_openfga_write_payload(tuples, "01MODEL")
    assert payload == {
        "writes": {"tuple_keys": tuples},
        "authorization_model_id": "01MODEL",
    }
    assert normalize_openfga_write_payload({}) is None

    read_resp = {"tuples": [{"key": tuples[0]}, {"key": tuples[1]}]}
    extracted = extract_read_tuples(read_resp)
    assert len(extracted) == 2
    assert len(filter_tuples_by_path(extracted, "document/roadmap")) == 1
    assert len(filter_tuples_by_path(extracted, "document/roadmap/owner")) == 1
    assert len(filter_tuples_by_path(extracted, "user:bob")) == 1


def test_factory_and_auth_validation():
    client = PolicyStoreClientFactory.create(
        store_type=PolicyStoreTypes.OPENFGA,
        url="http://localhost:8080",
        save_to_cache=False,
    )
    assert isinstance(client, OpenFGAClient)

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
            oauth_client_id="client-only",
        )


@pytest.mark.asyncio
async def test_openfga_transactions_and_readiness():
    client = OpenFGAClient(
        openfga_server_url="http://localhost:8080",
        store_id="01STORE",
        authorization_model_id="01MODEL",
    )
    assert not await client.is_ready()
    assert not await client.is_healthy()

    await client.log_transaction(
        StoreTransaction(
            id="tx-policy",
            actions=["set_policies"],
            transaction_type=TransactionType.policy,
            success=True,
        )
    )
    await client.log_transaction(
        StoreTransaction(
            id="tx-data",
            actions=["set_policy_data"],
            transaction_type=TransactionType.data,
            success=True,
        )
    )
    assert await client.is_ready()
    assert await client.is_healthy()
    client._set_engine_reachable(False)
    assert not await client.is_healthy()


def test_build_query_body_for_check_and_expand():
    client = OpenFGAClient(
        openfga_server_url="http://localhost:8080",
        store_id="01STORE",
        authorization_model_id="01MODEL",
    )
    check_body = client._build_query_body(
        "check",
        {
            "user": "user:alice",
            "relation": "viewer",
            "object": "document:roadmap",
        },
    )
    assert check_body["tuple_key"]["user"] == "user:alice"
    assert check_body["authorization_model_id"] == "01MODEL"

    expand_body = client._build_query_body(
        "expand",
        {"relation": "viewer", "object": "document:roadmap"},
    )
    assert expand_body["tuple_key"] == {
        "relation": "viewer",
        "object": "document:roadmap",
    }
