"""Comprehensive unit and integration tests for the OpenFGA policy store
client, DSL/JSON/YAML parser, runner, factory, and liveness probe."""

import asyncio
import contextlib
import io
import json
import os
import ssl
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from aiohttp import web
from fastapi import status
from opal_client.client import OpalClient
from opal_client.config import EngineLogFormat, opal_client_config
from opal_client.engine.options import LogLevel, OpenFGAServerOptions
from opal_client.engine.runner import OpenFGARunner, redact_engine_arguments
from opal_client.policy_store.openfga_client import (
    MAX_TUPLES_PER_WRITE,
    OpenFGAClient,
    _extract_tuple_list,
    _parse_condition_param_type,
    _parse_direct_type_entry,
    _parse_relation_expr,
    _split_top_level,
    _tuple_matches_path,
    extract_tuples_from_data,
    merge_openfga_models,
    normalize_tuple_key,
    parse_fga_dsl,
    parse_openfga_model,
    proxy_openfga_response_unless_invalid,
    tuple_identity,
)
from opal_client.policy_store.policy_store_client_factory import (
    PolicyStoreClientFactory,
)
from opal_client.policy_store.schemas import PolicyStoreAuth, PolicyStoreTypes
from opal_client.tests.opa_client_test import TEST_CA_CERT
from opal_common.git_utils.bundle_maker import BundleMaker
from opal_common.schemas.policy import DataModule, DeletedFiles, PolicyBundle, RegoModule
from opal_common.schemas.store import JSONPatchAction, StoreTransaction, TransactionType
from pydantic import BaseModel


class _CheckInputModel(BaseModel):
    user: Optional[str] = None
    relation: Optional[str] = None
    object: Optional[str] = None
    tuple_key: Optional[Dict[str, str]] = None
    authorization_model_id: Optional[str] = None


class _MockOpenFGAServer:
    """In-memory aiohttp server emulating the OpenFGA HTTP API for unit and
    integration tests."""

    def __init__(self) -> None:
        self.healthy: bool = True
        self.fail_status: Optional[int] = None
        self.stores: Dict[str, Dict[str, Any]] = {}
        self.models: Dict[str, List[Dict[str, Any]]] = {}
        self.tuples: Dict[str, List[Dict[str, Any]]] = {}
        self.write_calls: List[Dict[str, Any]] = []
        self.last_headers: Dict[str, str] = {}
        self.paginate_stores: bool = False
        self.paginate_tuples: bool = False
        self.return_non_json_error: bool = False
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.port: int = 0

    async def start(self) -> str:
        app = web.Application()
        app.router.add_get("/healthz", self._handle_healthz)
        app.router.add_post("/oauth/token", self._handle_oauth_token)
        app.router.add_get("/stores", self._handle_list_stores)
        app.router.add_post("/stores", self._handle_create_store)
        app.router.add_post(
            "/stores/{store_id}/authorization-models", self._handle_write_model
        )
        app.router.add_get(
            "/stores/{store_id}/authorization-models", self._handle_list_models
        )
        app.router.add_get(
            "/stores/{store_id}/authorization-models/{model_id}",
            self._handle_get_model,
        )
        app.router.add_post("/stores/{store_id}/write", self._handle_write_tuples)
        app.router.add_post("/stores/{store_id}/read", self._handle_read_tuples)
        app.router.add_post("/stores/{store_id}/check", self._handle_check)
        app.router.add_post("/stores/{store_id}/expand", self._handle_expand)
        app.router.add_post(
            "/stores/{store_id}/list-objects", self._handle_list_objects
        )
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await self._site.start()
        sockets = self._site._server.sockets  # type: ignore[union-attr]
        self.port = sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{self.port}"

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()

    def _check_forced_error(self) -> Optional[web.Response]:
        if self.fail_status is not None:
            if self.return_non_json_error:
                return web.Response(
                    status=self.fail_status,
                    text="plain text failure",
                    content_type="text/plain",
                )
            return web.json_response(
                {"code": "internal_error", "message": "forced failure"},
                status=self.fail_status,
            )
        return None

    async def _handle_healthz(self, request: web.Request) -> web.Response:
        if self.healthy:
            return web.json_response({"status": "SERVING"}, status=200)
        return web.json_response({"status": "NOT_SERVING"}, status=503)

    async def _handle_oauth_token(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"access_token": "mock-oauth-jwt-token", "expires_in": 3600},
            status=200,
        )

    async def _handle_list_stores(self, request: web.Request) -> web.Response:
        self.last_headers = dict(request.headers)
        err = self._check_forced_error()
        if err:
            return err

        store_list = list(self.stores.values())
        token = request.query.get("continuation_token")
        if self.paginate_stores and not token and len(store_list) > 1:
            return web.json_response(
                {"stores": store_list[:1], "continuation_token": "next-page"},
                status=200,
            )
        if self.paginate_stores and token == "next-page":
            return web.json_response(
                {"stores": store_list[1:], "continuation_token": ""},
                status=200,
            )
        return web.json_response(
            {"stores": store_list, "continuation_token": ""}, status=200
        )

    async def _handle_create_store(self, request: web.Request) -> web.Response:
        self.last_headers = dict(request.headers)
        err = self._check_forced_error()
        if err:
            return err

        body = await request.json()
        store_id = f"store-{len(self.stores) + 1:04d}"
        store_obj = {"id": store_id, "name": body.get("name", "opal")}
        self.stores[store_id] = store_obj
        self.models.setdefault(store_id, [])
        self.tuples.setdefault(store_id, [])
        return web.json_response(store_obj, status=201)

    async def _handle_write_model(self, request: web.Request) -> web.Response:
        self.last_headers = dict(request.headers)
        err = self._check_forced_error()
        if err:
            return err

        store_id = request.match_info["store_id"]
        body = await request.json()
        store_models = self.models.setdefault(store_id, [])
        model_id = f"model-{len(store_models) + 1:04d}"
        model_record = {"id": model_id, **body}
        store_models.append(model_record)
        return web.json_response({"authorization_model_id": model_id}, status=201)

    async def _handle_list_models(self, request: web.Request) -> web.Response:
        self.last_headers = dict(request.headers)
        err = self._check_forced_error()
        if err:
            return err

        store_id = request.match_info["store_id"]
        return web.json_response(
            {"authorization_models": self.models.get(store_id, [])}, status=200
        )

    async def _handle_get_model(self, request: web.Request) -> web.Response:
        self.last_headers = dict(request.headers)
        err = self._check_forced_error()
        if err:
            return err

        store_id = request.match_info["store_id"]
        model_id = request.match_info["model_id"]
        for m in self.models.get(store_id, []):
            if m["id"] == model_id:
                return web.json_response({"authorization_model": m}, status=200)
        return web.json_response({"code": "not_found"}, status=404)

    async def _handle_write_tuples(self, request: web.Request) -> web.Response:
        self.last_headers = dict(request.headers)
        err = self._check_forced_error()
        if err:
            return err

        store_id = request.match_info["store_id"]
        body = await request.json()
        self.write_calls.append(body)
        store_tuples = self.tuples.setdefault(store_id, [])

        deletes = body.get("deletes", {}).get("tuple_keys", [])
        for d in deletes:
            d_ident = (d["user"], d["relation"], d["object"])
            store_tuples[:] = [
                t
                for t in store_tuples
                if (t["user"], t["relation"], t["object"]) != d_ident
            ]

        writes = body.get("writes", {}).get("tuple_keys", [])
        for w in writes:
            w_ident = (w["user"], w["relation"], w["object"])
            store_tuples[:] = [
                t
                for t in store_tuples
                if (t["user"], t["relation"], t["object"]) != w_ident
            ]
            store_tuples.append(dict(w))

        return web.json_response({}, status=200)

    async def _handle_read_tuples(self, request: web.Request) -> web.Response:
        self.last_headers = dict(request.headers)
        err = self._check_forced_error()
        if err:
            return err

        store_id = request.match_info["store_id"]
        body = await request.json()
        store_tuples = list(self.tuples.get(store_id, []))
        tk_filter = body.get("tuple_key")
        if isinstance(tk_filter, dict):
            for k in ("user", "relation", "object"):
                if tk_filter.get(k):
                    store_tuples = [
                        t for t in store_tuples if t.get(k) == tk_filter[k]
                    ]

        wrapped = [{"key": t, "timestamp": "2026-01-01T00:00:00Z"} for t in store_tuples]
        token = body.get("continuation_token")
        if self.paginate_tuples and not token and len(wrapped) > 1:
            return web.json_response(
                {"tuples": wrapped[:1], "continuation_token": "tuple-page-2"},
                status=200,
            )
        if self.paginate_tuples and token == "tuple-page-2":
            return web.json_response(
                {"tuples": wrapped[1:], "continuation_token": ""},
                status=200,
            )
        return web.json_response(
            {"tuples": wrapped, "continuation_token": ""}, status=200
        )

    async def _handle_check(self, request: web.Request) -> web.Response:
        self.last_headers = dict(request.headers)
        err = self._check_forced_error()
        if err:
            return err

        store_id = request.match_info["store_id"]
        body = await request.json()
        tk = body.get("tuple_key", {})
        user = tk.get("user")
        relation = tk.get("relation")
        obj = tk.get("object")
        store_tuples = self.tuples.get(store_id, [])
        allowed = any(
            t.get("user") == user
            and t.get("relation") == relation
            and t.get("object") == obj
            for t in store_tuples
        )
        return web.json_response(
            {
                "allowed": allowed,
                "authorization_model_id": body.get("authorization_model_id"),
            },
            status=200,
        )

    async def _handle_expand(self, request: web.Request) -> web.Response:
        body = await request.json()
        return web.json_response({"tree": {"root": body.get("tuple_key")}}, status=200)

    async def _handle_list_objects(self, request: web.Request) -> web.Response:
        store_id = request.match_info["store_id"]
        body = await request.json()
        user = body.get("user")
        relation = body.get("relation")
        obj_type = body.get("type", "")
        objs = [
            t["object"]
            for t in self.tuples.get(store_id, [])
            if t.get("user") == user
            and t.get("relation") == relation
            and t.get("object", "").startswith(f"{obj_type}:")
        ]
        return web.json_response({"objects": objs}, status=200)


@contextlib.asynccontextmanager
async def _mock_openfga() -> AsyncIterator[Tuple[_MockOpenFGAServer, str]]:
    server = _MockOpenFGAServer()
    base_url = await server.start()
    try:
        yield server, base_url
    finally:
        await server.stop()


@contextlib.asynccontextmanager
async def _override_config(**overrides):
    saved = {key: getattr(opal_client_config, key) for key in overrides}
    try:
        for key, value in overrides.items():
            setattr(opal_client_config, key, value)
        yield
    finally:
        for key, value in saved.items():
            setattr(opal_client_config, key, value)


# ============================================================================
# 1. Unit Tests: OpenFGA DSL / JSON / YAML Parser & Model Merger
# ============================================================================


def test_parse_fga_dsl_comprehensive():
    dsl = """
    # Sample ReBAC model with conditions, unions, intersections, exclusions, and tuple-to-userset
    model
      schema 1.1

    type user

    type group
      relations
        define member: [user, user:*]

    extend type group
      relations
        define admin: [user]

    type folder
      relations
        define parent: [folder]
        define viewer: [user, group#member]

    type document
      relations
        define parent: [folder]
        define blocked: [user]
        define owner: [user with non_expired_grant]
        define editor: ([user] or owner) and viewer from parent
        define viewer: ([user, group#member with non_expired_grant] or editor) but not blocked
        define empty_rel: []

    condition non_expired_grant(current_time: timestamp, grant_duration: duration, tags: list<string>, meta: map<int>) {
      current_time < timestamp("2030-01-01T00:00:00Z") &&
      size(tags) > 0
    }

    condition single_line_cond(ip: ipaddress) { true }
    """
    model = parse_fga_dsl(dsl)
    assert model["schema_version"] == "1.1"
    types_by_name = {td["type"]: td for td in model["type_definitions"]}
    assert set(types_by_name.keys()) == {"user", "group", "folder", "document"}
    assert types_by_name["user"]["relations"] == {}
    assert types_by_name["user"]["metadata"] is None

    # group has both member and extended admin
    assert "member" in types_by_name["group"]["relations"]
    assert "admin" in types_by_name["group"]["relations"]
    member_meta = types_by_name["group"]["metadata"]["relations"]["member"][
        "directly_related_user_types"
    ]
    assert {"type": "user"} in member_meta
    assert {"type": "user", "wildcard": {}} in member_meta

    # document relations
    doc_rels = types_by_name["document"]["relations"]
    assert "intersection" in doc_rels["editor"]
    assert "difference" in doc_rels["viewer"]
    assert doc_rels["empty_rel"] == {"this": {}}

    # conditions
    assert "non_expired_grant" in model["conditions"]
    cond = model["conditions"]["non_expired_grant"]
    assert cond["parameters"]["current_time"] == {"type_name": "TYPE_NAME_TIMESTAMP"}
    assert cond["parameters"]["tags"] == {
        "type_name": "TYPE_NAME_LIST",
        "generic_types": [{"type_name": "TYPE_NAME_STRING"}],
    }
    assert "single_line_cond" in model["conditions"]


def test_parse_fga_dsl_module_and_edge_cases():
    mod_dsl = """
    module core
    type doc
      relations
        define reader: [user]
        define writer: (reader)
        define commenter: reader from parent
    condition cond_trailing_brace(x: string) {
      x == "ok" }
    """
    parsed = parse_openfga_model(mod_dsl, policy_id="core.fga")
    assert parsed["type_definitions"][0]["type"] == "doc"
    assert parsed["type_definitions"][0]["relations"]["writer"] == {
        "computedUserset": {"relation": "reader"}
    }
    assert "tupleToUserset" in parsed["type_definitions"][0]["relations"]["commenter"]


def test_parse_fga_dsl_errors():
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_openfga_model("   ")

    with pytest.raises(ValueError, match="Unexpected 'relations'"):
        parse_fga_dsl("relations\n  define viewer: [user]")

    with pytest.raises(ValueError, match="Unrecognized OpenFGA DSL line"):
        parse_fga_dsl("model\n  schema 1.1\n  invalid_syntax_here")

    with pytest.raises(ValueError, match="Invalid 'but not'"):
        _parse_relation_expr("[user] but not a but not b")

    with pytest.raises(ValueError, match="Unsupported or invalid OpenFGA relation"):
        _parse_relation_expr("invalid expression $$$")

    with pytest.raises(ValueError, match="Unknown OpenFGA condition parameter type"):
        _parse_condition_param_type("unknown_type")

    with pytest.raises(ValueError, match="Invalid condition parameter"):
        parse_fga_dsl("condition bad_cond(no_type_colon) { true }")


def test_parse_openfga_model_json_and_yaml():
    json_model = json.dumps(
        {
            "schema_version": "1.1",
            "type_definitions": [{"type": "user", "relations": {}}],
        }
    )
    parsed_json = parse_openfga_model(json_model, policy_id="model.json")
    assert parsed_json["type_definitions"][0]["type"] == "user"

    # Invalid JSON with .json suffix
    with pytest.raises(ValueError, match="Invalid OpenFGA JSON model"):
        parse_openfga_model("{not-valid-json", policy_id="bad.json")

    # JSON missing type_definitions
    with pytest.raises(ValueError, match="type_definitions"):
        parse_openfga_model('{"hello": "world"}', policy_id="bad.json")

    # YAML with type_definitions
    yaml_model = """
    schema_version: "1.1"
    type_definitions:
      - type: user
        relations: {}
    """
    parsed_yaml = parse_openfga_model(yaml_model, policy_id="model.yaml")
    assert parsed_yaml["type_definitions"][0]["type"] == "user"

    # YAML with embedded DSL model string
    yaml_dsl = """
    model: |
      model
        schema 1.1
      type user
    """
    parsed_yaml_dsl = parse_openfga_model(yaml_dsl, policy_id="fga.yml")
    assert parsed_yaml_dsl["type_definitions"][0]["type"] == "user"

    # Invalid YAML
    with pytest.raises(ValueError, match="Invalid OpenFGA YAML model"):
        parse_openfga_model(":\n  - [\ninvalid yaml", policy_id="bad.yaml")

    with pytest.raises(ValueError, match="YAML policy must contain"):
        parse_openfga_model("foo: bar", policy_id="bad.yaml")

    # Fallback JSON when no policy_id suffix is given but content doesn't start with '{'
    # and fallback DSL when no policy_id suffix is given
    fallback_dsl = parse_openfga_model(
        "# comment first\nmodel\n  schema 1.1\ntype user"
    )
    assert fallback_dsl["type_definitions"][0]["type"] == "user"


def test_merge_openfga_models():
    assert merge_openfga_models({}) == {
        "schema_version": "1.1",
        "type_definitions": [],
    }

    m1 = parse_fga_dsl("model\n  schema 1.1\ntype user\ntype doc\n  relations\n    define owner: [user]")
    single_merged = merge_openfga_models({"a.fga": m1})
    assert len(single_merged["type_definitions"]) == 2

    m2 = parse_fga_dsl(
        "module ext\nextend type doc\n  relations\n    define viewer: [user] or owner\n"
        "condition c1(x: int) { x > 0 }"
    )
    # Test merging when first definition had metadata=None
    m_no_meta = {"schema_version": "1.1", "type_definitions": [{"type": "doc", "relations": {}, "metadata": None}]}
    merged = merge_openfga_models({"01.fga": m_no_meta, "02.fga": m1, "03.fga": m2})
    doc_td = next(td for td in merged["type_definitions"] if td["type"] == "doc")
    assert "owner" in doc_td["relations"]
    assert "viewer" in doc_td["relations"]
    assert "c1" in merged["conditions"]


# ============================================================================
# 2. Unit Tests: Tuple Extraction, Normalization & Path Matching
# ============================================================================


def test_extract_and_normalize_tuples():
    assert normalize_tuple_key("not-a-dict") is None
    assert normalize_tuple_key({"user": "user:a"}) is None
    tk_with_cond = normalize_tuple_key(
        {
            "key": {
                "user": "user:anne",
                "relation": "viewer",
                "object": "document:1",
                "condition": {"name": "c1"},
            }
        }
    )
    assert tk_with_cond == {
        "user": "user:anne",
        "relation": "viewer",
        "object": "document:1",
        "condition": {"name": "c1"},
    }
    assert _extract_tuple_list("invalid") == []

    # List input
    t_list, w, d = extract_tuples_from_data(
        [{"user": "user:anne", "relation": "viewer", "object": "document:1"}]
    )
    assert len(t_list) == 1 and w == [] and d == []

    # Explicit writes/deletes input
    t_none, w, d = extract_tuples_from_data(
        {
            "writes": {"tuple_keys": [{"user": "user:a", "relation": "r", "object": "o:1"}]},
            "deletes": [{"user": "user:b", "relation": "r", "object": "o:1"}],
        }
    )
    assert t_none is None and len(w) == 1 and len(d) == 1

    # tuple_keys input
    t_keys, _, _ = extract_tuples_from_data(
        {"tuple_keys": [{"user": "user:a", "relation": "r", "object": "o:1"}]}
    )
    assert len(t_keys) == 1

    # Single tuple dict
    t_single, _, _ = extract_tuples_from_data(
        {"user": "user:a", "relation": "r", "object": "o:1"}
    )
    assert len(t_single) == 1

    # Scoped path object mapping (e.g. path="/document:roadmap" and path="/document/roadmap")
    t_scoped1, _, _ = extract_tuples_from_data(
        {"viewer": ["user:anne", "user:bob"]}, path="/document:roadmap"
    )
    assert len(t_scoped1) == 2
    assert t_scoped1[0]["object"] == "document:roadmap"

    t_scoped2, _, _ = extract_tuples_from_data(
        {"editor": ["user:anne"]}, path="/document/roadmap"
    )
    assert t_scoped2 == [
        {"user": "user:anne", "relation": "editor", "object": "document:roadmap"}
    ]

    # Hierarchical mapping (both `type:id` keys, nested `{type: {id: {rel: [users]}}}`, and list values)
    t_hier, _, _ = extract_tuples_from_data(
        {
            "document:1": {"viewer": ["user:anne"]},
            "folder": {"eng": {"owner": ["user:bob"]}},
            "extra_list": [{"user": "user:charlie", "relation": "admin", "object": "org:acme"}],
        }
    )
    assert len(t_hier) == 3

    with pytest.raises(ValueError, match="Unsupported policy_data type"):
        extract_tuples_from_data(12345)


def test_tuple_matches_path():
    tk = {"user": "user:anne", "relation": "viewer", "object": "document:roadmap"}
    assert _tuple_matches_path(tk, "") is True
    assert _tuple_matches_path(tk, "/") is True
    assert _tuple_matches_path(tk, "/tuples") is True
    assert _tuple_matches_path(tk, "/document:roadmap") is True
    assert _tuple_matches_path(tk, "/document") is True
    assert _tuple_matches_path(tk, "/document/roadmap") is True
    assert _tuple_matches_path(tk, "/document/roadmap/viewer") is True
    assert _tuple_matches_path(tk, "/document/roadmap/editor") is False
    assert _tuple_matches_path(tk, "/folder:eng") is False


# ============================================================================
# 3. Unit Tests: OpenFGAClient Auth, TLS, Store Creation, Policies & Tuples
# ============================================================================


def test_openfga_client_auth_and_tls_validation(tmpdir):
    with pytest.raises(ValueError, match="required variables for token auth"):
        OpenFGAClient(
            server_url="http://localhost:8080",
            auth_token=None,
            auth_type=PolicyStoreAuth.TOKEN,
        )

    with pytest.raises(ValueError, match="required variables for oauth"):
        OpenFGAClient(
            server_url="http://localhost:8080",
            auth_type=PolicyStoreAuth.OAUTH,
            oauth_client_id=None,
            oauth_client_secret=None,
            oauth_server=None,
        )

    with pytest.raises(ValueError, match="required variables for tls"):
        OpenFGAClient(
            server_url="http://localhost:8080",
            auth_type=PolicyStoreAuth.TLS,
            tls_client_cert=None,
            tls_client_key=None,
            tls_ca=None,
        )

    ca_path = os.path.join(tmpdir, "ca.pem")
    with open(ca_path, "w") as f:
        f.write(TEST_CA_CERT)

    client = OpenFGAClient(
        server_url="http://localhost:8080",
        auth_type=PolicyStoreAuth.NONE,
        tls_ca=ca_path,
        cache_policy_data=True,
    )
    assert client._custom_ssl_context is not None
    with patch.object(ssl.SSLContext, "load_cert_chain") as mock_load_cert:
        client_mtls = OpenFGAClient(
            server_url="http://localhost:8080",
            auth_type=PolicyStoreAuth.TLS,
            tls_ca=ca_path,
            tls_client_cert=ca_path,
            tls_client_key=ca_path,
        )
        assert client_mtls._custom_ssl_context is not None
        mock_load_cert.assert_called_once_with(certfile=ca_path, keyfile=ca_path)


@pytest.mark.asyncio
async def test_openfga_store_discovery_pagination_and_oauth():
    async with _mock_openfga() as (server, base_url):
        server.stores["store-other"] = {"id": "store-other", "name": "other"}
        server.stores["store-target"] = {"id": "store-target", "name": "my-store"}
        server.paginate_stores = True

        client = OpenFGAClient(
            server_url=base_url,
            store_name="my-store",
            auth_type=PolicyStoreAuth.OAUTH,
            oauth_client_id="cid",
            oauth_client_secret="csecret",
            oauth_server=f"{base_url}/oauth/token",
        )
        async with aiohttp.ClientSession() as session:
            resolved_id = await client._ensure_store_id(session)
            assert resolved_id == "store-target"
            assert server.last_headers.get("Authorization") == "Bearer mock-oauth-jwt-token"
            # Second call returns cached _store_id immediately
            assert await client._ensure_store_id(session) == "store-target"


@pytest.mark.asyncio
async def test_openfga_policies_crud_and_bundles():
    async with _mock_openfga() as (server, base_url):
        client = OpenFGAClient(
            server_url=base_url,
            store_name="opal-crud",
            auth_type=PolicyStoreAuth.TOKEN,
            auth_token="secret-token",
        )
        assert await client.get_policy_module_ids() == []

        dsl_code = """
        model
          schema 1.1
        type user
        type document
          relations
            define viewer: [user]
        """
        resp = await client.set_policy("model.fga", dsl_code)
        assert resp is not None and resp.status_code == status.HTTP_201_CREATED
        assert client._authorization_model_id == "model-0001"
        assert server.last_headers.get("Authorization") == "Bearer secret-token"

        assert await client.get_policy("model.fga") == dsl_code
        assert await client.get_policy("model-0001") is not None
        assert await client.get_policy("nonexistent") is None
        assert await client.get_policy_module_ids() == ["model.fga"]

        # Test get_policies when _authorization_model_id is None (lists all models)
        saved_model_id = client._authorization_model_id
        client._authorization_model_id = None
        all_policies = await client.get_policies()
        assert "model-0001" in all_policies
        client._raw_policies.clear()
        client._authorization_model_id = saved_model_id
        assert await client.get_policy_module_ids() == [saved_model_id]
        client._raw_policies["model.fga"] = dsl_code

        # Add a second module and then delete the first
        ext_code = """
        module ext
        extend type document
          relations
            define editor: [user]
        """
        await client.set_policy("ext.fga", ext_code)
        assert client._authorization_model_id == "model-0002"

        del_resp = await client.delete_policy("ext.fga")
        assert del_resp is not None and del_resp.status_code == status.HTTP_201_CREATED
        assert client._authorization_model_id == "model-0003"

        # Delete the last remaining policy
        del_last = await client.delete_policy("model.fga")
        assert del_last is not None and del_last.status_code == status.HTTP_200_OK
        assert client._authorization_model_id is None

        # Test ignore paths
        async with _override_config(POLICY_STORE_POLICY_PATHS_TO_IGNORE=["ignored/**"]):
            assert await client.set_policy("ignored/model.fga", dsl_code) is None
            assert await client.delete_policy("ignored/model.fga") is None
            assert await client.set_policy_data({"tuples": []}, path="ignored/data") is None
            assert await client.delete_policy_data(path="ignored/data") is None
            assert await client.patch_policy_data([], path="ignored/data") is None


@pytest.mark.asyncio
async def test_openfga_set_policies_bundle_and_diff_bundle():
    async with _mock_openfga() as (server, base_url):
        client = OpenFGAClient(server_url=base_url, store_name="bundle-store")

        dsl = "model\n  schema 1.1\ntype user\ntype document\n  relations\n    define viewer: [user]\n    define editor: [user]"
        tuples_json = json.dumps(
            {
                "tuples": [
                    {"user": "user:anne", "relation": "viewer", "object": "document:1"},
                    {"user": "user:bob", "relation": "editor", "object": "document:1"},
                ]
            }
        )
        bundle1 = PolicyBundle(
            manifest=["model.fga", "data.json"],
            hash="commit-1",
            policy_modules=[
                RegoModule(path="model.fga", package_name="", rego=dsl),
            ],
            data_modules=[
                DataModule(path="", data=tuples_json),
                DataModule(path="", data="{invalid-json-is-skipped"),
            ],
        )
        await client.set_policies(bundle1)
        assert await client.get_policy_version() == "commit-1"
        data_after_b1 = await client.get_data()
        assert len(data_after_b1["tuples"]) == 2

        # Diff bundle with mismatched old_hash, deleting data and policy
        bundle2 = PolicyBundle(
            manifest=[],
            hash="commit-2",
            old_hash="wrong-old-hash",
            policy_modules=[],
            data_modules=[],
            deleted_files=DeletedFiles(
                policy_modules=[Path("model.fga")],
                data_modules=[""],
            ),
        )
        await client.set_policies(bundle2)
        assert await client.get_policy_version() == "commit-2"
        assert client._authorization_model_id is None
        assert (await client.get_data())["tuples"] == []


@pytest.mark.asyncio
async def test_openfga_data_reconciliation_batching_patching_and_check():
    async with _mock_openfga() as (server, base_url):
        client = OpenFGAClient(server_url=base_url, store_name="data-store")
        dsl = "model\n  schema 1.1\ntype user\ntype document\n  relations\n    define viewer: [user]\n    define editor: [user]"
        await client.set_policy("model.fga", dsl)

        # 1. Batch write > MAX_TUPLES_PER_WRITE (e.g., 120 tuples)
        many_tuples = [
            {"user": f"user:{i}", "relation": "viewer", "object": "document:bulk"}
            for i in range(120)
        ]
        await client.set_policy_data({"tuples": many_tuples})
        server.paginate_tuples = True
        fetched = await client.get_data(path="/document:bulk")
        assert len(fetched["tuples"]) == 120
        server.paginate_tuples = False

        # 2. Replace with 2 tuples (triggers batched delete of 120 + write of 2)
        small_tuples = [
            {"user": "user:anne", "relation": "viewer", "object": "document:roadmap"},
            {"user": "user:bob", "relation": "editor", "object": "document:roadmap"},
        ]
        await client.set_policy_data({"tuples": small_tuples})
        assert len((await client.get_data())["tuples"]) == 2

        # 3. Explicit writes and deletes
        await client.set_policy_data(
            {
                "writes": [
                    {
                        "user": "user:charlie",
                        "relation": "viewer",
                        "object": "document:roadmap",
                    }
                ],
                "deletes": [
                    {
                        "user": "user:bob",
                        "relation": "editor",
                        "object": "document:roadmap",
                    }
                ],
            }
        )
        current = (await client.get_data())["tuples"]
        users = {t["user"] for t in current}
        assert users == {"user:anne", "user:charlie"}

        # 4. Patch policy data (direct add/remove tuple objects)
        await client.patch_policy_data(
            [
                JSONPatchAction(
                    op="add",
                    path="/tuples/-",
                    value={
                        "user": "user:dave",
                        "relation": "editor",
                        "object": "document:roadmap",
                    },
                ),
                JSONPatchAction(
                    op="remove",
                    path="/tuples/0",
                    value={
                        "user": "user:charlie",
                        "relation": "viewer",
                        "object": "document:roadmap",
                    },
                ),
            ]
        )
        users_after_direct_patch = {t["user"] for t in (await client.get_data())["tuples"]}
        assert users_after_direct_patch == {"user:anne", "user:dave"}

        # 5. Patch policy data (standard RFC 6902 JSONPatch on /tuples/0/relation)
        await client.patch_policy_data(
            [
                JSONPatchAction(
                    op="replace",
                    path="/0/relation",
                    value="editor",
                )
            ],
            path="tuples",
        )
        anne_tuple = next(
            t for t in (await client.get_data())["tuples"] if t["user"] == "user:anne"
        )
        assert anne_tuple["relation"] == "editor"

        # 6. get_data_with_input (/check, /expand, /list-objects, dict & Pydantic inputs)
        check_resp = await client.get_data_with_input(
            "check",
            _CheckInputModel(
                user="user:anne", relation="editor", object="document:roadmap"
            ),
        )
        assert json.loads(check_resp.body) == {
            "allowed": True,
            "authorization_model_id": client._authorization_model_id,
        }

        # Dict input and /list-objects endpoint
        list_obj_resp = await client.get_data_with_input(
            "/list-objects",
            {"user": "user:anne", "relation": "editor", "type": "document"},  # type: ignore[arg-type]
        )
        assert json.loads(list_obj_resp.body) == {"objects": ["document:roadmap"]}

        # Legacy .dict() object input
        class _LegacyV1Input:
            def dict(self, exclude_none=True):
                return {
                    "tuple_key": {
                        "user": "user:nobody",
                        "relation": "editor",
                        "object": "document:roadmap",
                    }
                }

        legacy_resp = await client.get_data_with_input("", _LegacyV1Input())  # type: ignore[arg-type]
        assert json.loads(legacy_resp.body)["allowed"] is False

        with pytest.raises(TypeError, match="Unsupported input type"):
            await client.get_data_with_input("check", 42)  # type: ignore[arg-type]

        # 7. Export and Import
        class _AsyncStringFile:
            def __init__(self, initial: str = ""):
                self.buf = io.StringIO(initial)

            async def write(self, data: str):
                self.buf.write(data)

            async def read(self) -> str:
                return self.buf.getvalue()

        export_file = _AsyncStringFile()
        await client.full_export(export_file)  # type: ignore[arg-type]
        exported_str = export_file.buf.getvalue()
        assert "document:roadmap" in exported_str

        # Delete via set_policy_data(None)
        await client.set_policy_data(None)
        assert (await client.get_data())["tuples"] == []

        # Re-import from backup
        import_file = _AsyncStringFile(exported_str)
        await client.full_import(import_file)  # type: ignore[arg-type]
        assert len((await client.get_data())["tuples"]) == 2


@pytest.mark.asyncio
async def test_openfga_error_handling_and_transactions():
    async with _mock_openfga() as (server, base_url):
        async with _override_config():
            client = OpenFGAClient(
                server_url=base_url,
                store_id="store-err",
            )
            await client.init_healthcheck_policy("hc", "code")

            # Unexpected status code with JSON error and non-JSON error
            server.fail_status = 400
            with pytest.raises(ValueError, match="unexpected status code: 400"):
                await client.get_data()

            server.return_non_json_error = True
            with pytest.raises(ValueError, match="plain text failure"):
                await client.get_data()
            server.fail_status = None
            server.return_non_json_error = False

            # Transaction logging and readiness/healthiness
            assert await client.is_ready() is False
            await client.log_transaction(
                StoreTransaction(
                    id="tx-1",
                    actions=["set_policies"],
                    transaction_type=TransactionType.policy,
                    success=True,
                )
            )
            await client.log_transaction(
                StoreTransaction(
                    id="tx-2",
                    actions=["set_policy_data"],
                    transaction_type=TransactionType.data,
                    success=True,
                )
            )
            assert await client.is_ready() is True
            assert await client.is_healthy() is True


# ============================================================================
# 4. Liveness Probe Tests for OpenFGAClient
# ============================================================================


@pytest.mark.asyncio
async def test_openfga_liveness_probe_lifecycle():
    async with _mock_openfga() as (server, base_url):
        async with _override_config(
            POLICY_STORE_LIVENESS_PROBE_ENABLED=True,
            POLICY_STORE_LIVENESS_PROBE_INTERVAL_SECONDS=1,
            POLICY_STORE_LIVENESS_PROBE_TIMEOUT_SECONDS=1,
        ):
            client = OpenFGAClient(server_url=base_url, store_id="store-1")
            await client.log_transaction(
                StoreTransaction(
                    id="t1",
                    actions=["set_policies"],
                    transaction_type=TransactionType.policy,
                    success=True,
                )
            )
            await client.log_transaction(
                StoreTransaction(
                    id="t2",
                    actions=["set_policy_data"],
                    transaction_type=TransactionType.data,
                    success=True,
                )
            )
            try:
                assert client._probe_log_label == "OpenFGA"
                await client.start_liveness_probe()
                assert client._get_engine_reachable() is True
                assert await client.is_healthy() is True

                # Flip OpenFGA to 503 unhealthy
                server.healthy = False
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and client._get_engine_reachable():
                    await asyncio.sleep(0.05)
                assert await client.is_healthy() is False

                # Flip OpenFGA back to 200 healthy
                server.healthy = True
                deadline = time.monotonic() + 5.0
                while (
                    time.monotonic() < deadline and not client._get_engine_reachable()
                ):
                    await asyncio.sleep(0.05)
                assert await client.is_healthy() is True
            finally:
                await client.stop_liveness_probe()


# ============================================================================
# 5. Runner, Options, Factory, OpalClient & BundleMaker Tests
# ============================================================================


def test_openfga_server_options_and_runner():
    opts = OpenFGAServerOptions(
        http_addr=":8080",
        grpc_addr="0.0.0.0:8081",
        datastore_engine="postgres",
        datastore_uri="postgres://user:secret@localhost:5432/openfga",
        authn_method="preshared",
        authn_preshared_keys="super-secret-key",
        playground_enabled=True,
        log_level=LogLevel.info,
    )
    args = list(opts.get_args())
    assert args == [
        "--http-addr",
        "0.0.0.0:8080",
        "--grpc-addr",
        "0.0.0.0:8081",
        "--datastore-engine",
        "postgres",
        "--datastore-uri",
        "postgres://user:secret@localhost:5432/openfga",
        "--authn-method",
        "preshared",
        "--authn-preshared-keys",
        "super-secret-key",
        "--playground-enabled",
        "--log-level",
        "info",
    ]
    # Redaction check
    redacted = redact_engine_arguments(args)
    assert "super-secret-key" not in redacted
    assert "postgres://user:secret@localhost:5432/openfga" not in redacted
    assert "super-secret-key" not in repr(opts)

    with pytest.raises(ValueError, match="Invalid http_addr"):
        OpenFGAServerOptions(http_addr="invalid_addr_without_colon")

    runner = OpenFGARunner.setup_openfga_runner(
        options=OpenFGAServerOptions(playground_enabled=False),
        piped_logs_format=EngineLogFormat.NONE,
        initial_start_callbacks=[AsyncMock()],
        rehydration_callbacks=[AsyncMock()],
    )
    assert runner.get_arguments() == [
        "run",
        "--http-addr",
        "0.0.0.0:8080",
        "--playground-enabled=false",
    ]
    with patch.object(opal_client_config, "INLINE_OPENFGA_EXEC_PATH", "/usr/bin/openfga"):
        assert runner.get_executable_path() == "/usr/bin/openfga"
    with patch.object(opal_client_config, "INLINE_OPENFGA_EXEC_PATH", None):
        with patch("shutil.which", return_value="/usr/local/bin/openfga"):
            assert runner.get_executable_path() == "/usr/local/bin/openfga"
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="OpenFGA executable not found"):
                runner.get_executable_path()

    bad_opts = OpenFGAServerOptions()
    bad_opts.http_addr = "bad_addr"
    with pytest.raises(ValueError, match="Invalid http_addr"):
        list(bad_opts.get_args())


@pytest.mark.asyncio
async def test_openfga_runner_health_check_and_factory():
    async with _mock_openfga() as (server, base_url):
        async with _override_config(POLICY_STORE_URL=base_url):
            runner = OpenFGARunner()
            assert await runner.health_check() is True
            assert await runner.handle_log_line(b"openfga started\n") is False
            server.healthy = False
            assert await runner.health_check() is False

        async with _override_config(POLICY_STORE_URL="http://127.0.0.1:1"):
            assert await runner.health_check() is False

        store = PolicyStoreClientFactory.create(
            store_type=PolicyStoreTypes.OPENFGA,
            url=base_url,
            save_to_cache=False,
        )
        assert isinstance(store, OpenFGAClient)

        opal_client = OpalClient(
            policy_store_type=PolicyStoreTypes.OPENFGA,
            policy_store=store,
            data_updater=False,
            policy_updater=False,
            inline_openfga_enabled=True,
        )
        assert isinstance(opal_client.engine_runner, OpenFGARunner)


def test_bundle_maker_get_module_package_name():
    rego_code = "package app.rbac\ndefault allow = false\n"
    fga_code = "model\n  schema 1.1\ntype user\n"
    assert (
        BundleMaker._get_module_package_name(Path("rbac.rego"), rego_code)
        == "app.rbac"
    )
    assert BundleMaker._get_module_package_name(Path("model.fga"), fga_code) == ""
    assert BundleMaker._get_module_package_name(Path("model.json"), "{}") == ""


# ============================================================================
# 6. End-to-End Integration Test: OPAL Policy + Data Sync with OpenFGA Store
# ============================================================================


@pytest.mark.asyncio
async def test_end_to_end_openfga_policy_and_data_sync_integration():
    """End-to-end integration test verifying that OPAL syncs an OpenFGA `.fga`
    ReBAC model and relationship tuples from data sources, evaluates `/check`
    queries accurately, and applies live incremental data updates."""
    async with _mock_openfga() as (_server, base_url):
        store = PolicyStoreClientFactory.create(
            store_type=PolicyStoreTypes.OPENFGA,
            url=base_url,
            save_to_cache=False,
        )

        # 1. Load the example ReBAC `.fga` model from docker/docker_files/openfga_policy/model.fga
        repo_root = Path(__file__).resolve().parents[4]
        fga_model_path = (
            repo_root / "docker" / "docker_files" / "openfga_policy" / "model.fga"
        )
        data_json_path = (
            repo_root / "docker" / "docker_files" / "openfga_data" / "data.json"
        )
        fga_dsl = fga_model_path.read_text(encoding="utf-8")
        initial_tuples = json.loads(data_json_path.read_text(encoding="utf-8"))

        bundle = PolicyBundle(
            manifest=["model.fga"],
            hash="e2e-commit-1",
            policy_modules=[
                RegoModule(path="model.fga", package_name="", rego=fga_dsl)
            ],
            data_modules=[],
        )
        await store.set_policies(bundle)
        await store.set_policy_data(initial_tuples)

        # Verify charlie is viewer on document:roadmap, but bob is not directly viewer on document:roadmap
        res_charlie = await store.get_data_with_input(
            "check",
            _CheckInputModel(
                user="user:charlie",
                relation="viewer",
                object="document:roadmap",
            ),
        )
        assert json.loads(res_charlie.body)["allowed"] is True

        res_diana_before = await store.get_data_with_input(
            "check",
            _CheckInputModel(
                user="user:diana",
                relation="editor",
                object="document:roadmap",
            ),
        )
        assert json.loads(res_diana_before.body)["allowed"] is False

        # 2. Simulate a live OPAL data update granting user:diana editor on document:roadmap
        updated_tuples = copy_tuples = list(initial_tuples["tuples"]) + [
            {
                "user": "user:diana",
                "relation": "editor",
                "object": "document:roadmap",
            }
        ]
        await store.set_policy_data({"tuples": updated_tuples})

        res_diana_after = await store.get_data_with_input(
            "check",
            _CheckInputModel(
                user="user:diana",
                relation="editor",
                object="document:roadmap",
            ),
        )
        assert json.loads(res_diana_after.body)["allowed"] is True


@pytest.mark.asyncio
async def test_openfga_remaining_edge_cases_and_client_errors():
    import tenacity

    # 1. _parse_relation_expr where leading '(' and trailing ')' do NOT wrap the entire expression
    rewrite, dtypes = _parse_relation_expr("([user]) or (owner)")
    assert "union" in rewrite
    assert dtypes == [{"type": "user"}]

    # 2. parse_fga_dsl with trailing comma in condition params and expression text on opening '{' line
    dsl_cond = """
    model
      schema 1.1
    type user
    condition multiline_cond(a: string, ) { a != "" &&
      a == "ok"
    }
    """
    parsed_cond = parse_fga_dsl(dsl_cond)
    assert parsed_cond["conditions"]["multiline_cond"]["expression"] == 'a != "" && a == "ok"'

    # 3. parse_openfga_model YAML syntax error and fallback without policy_id
    with pytest.raises(ValueError, match="Invalid OpenFGA YAML model"):
        parse_openfga_model("bad: [unclosed", policy_id="broken.yaml")

    # Fallback JSON when text has leading comment/space or no policy_id
    fallback_dsl = "schema 1.1\ntype user\n"
    assert parse_openfga_model(fallback_dsl, policy_id=None)["type_definitions"][0]["type"] == "user"

    # Mock json.loads to test fallback JSON branch (lines 452-458) when text doesn't start with '{'
    real_loads = json.loads
    with patch("opal_client.policy_store.openfga_client.json.loads") as mock_loads:
        mock_loads.side_effect = [
            {"type_definitions": [{"type": "user", "relations": {}}]},
        ]
        res_fallback_json = parse_openfga_model("not_starting_with_brace", policy_id="model.txt")
        assert res_fallback_json["schema_version"] == "1.1"

    with patch("opal_client.policy_store.openfga_client.json.loads", side_effect=real_loads):
        pass

    # 4. _write_merged_authorization_model non-JSON body tolerance, _read_all_tuples filter, and empty batch write
    async with _mock_openfga() as (_server, base_url):
        client = OpenFGAClient(server_url=base_url, store_id="store-edge")
        async with aiohttp.ClientSession() as session:
            empty_res = await client._write_and_delete_tuples_batched(
                session, "store-edge", [], []
            )
            assert empty_res.status_code == 200

            filtered_tuples = await client._read_all_tuples(
                session, "store-edge", tuple_key_filter={"object": "document:1"}
            )
            assert filtered_tuples == []

            with patch(
                "opal_client.policy_store.openfga_client.proxy_openfga_response_unless_invalid",
                AsyncMock(return_value=web.Response(status=201, body=b"not-json")),
            ):
                # Also cover line 932-933 when response.body is non-JSON
                from fastapi import Response as FastAPIResponse

                with patch(
                    "opal_client.policy_store.openfga_client.proxy_openfga_response_unless_invalid",
                    AsyncMock(
                        return_value=FastAPIResponse(
                            status_code=201, content=b"not-json"
                        )
                    ),
                ):
                    resp = await client._write_merged_authorization_model(session)
                    assert resp.status_code == 201

        # Cover set_policies ignored policy module and ignored data module (lines 1013, 1038)
        async with _override_config(POLICY_STORE_POLICY_PATHS_TO_IGNORE=["ignored/*"]):
            bundle_ignored = PolicyBundle(
                manifest=["ignored/m.fga"],
                hash="ign-1",
                policy_modules=[
                    RegoModule(
                        path="ignored/m.fga",
                        package_name="",
                        rego="model\n  schema 1.1\ntype user\n",
                    )
                ],
                data_modules=[
                    DataModule(path="ignored/data.json", data='{"tuples": []}')
                ],
            )
            await client.set_policies(bundle_ignored)

        # Cover delete_policy when policy_id == self._authorization_model_id (line 1140)
        client._authorization_model_id = "mod-to-del"
        await client.delete_policy("mod-to-del")
        assert client._authorization_model_id is None

    # 5. Cover aiohttp.ClientError exception handlers across all network methods
    dead_client = OpenFGAClient(
        server_url="http://127.0.0.1:1",
        store_id="s-dead",
        auth_type=PolicyStoreAuth.OAUTH,
        oauth_client_id="cid",
        oauth_client_secret="csec",
        oauth_server="http://127.0.0.1:1/oauth/token",
    )
    for method in (
        dead_client._get_oauth_token,
        dead_client.set_policy,
        dead_client.set_policies,
        dead_client.get_policies,
        dead_client.delete_policy,
        dead_client.set_policy_data,
        dead_client.delete_policy_data,
        dead_client.patch_policy_data,
        dead_client.get_data,
        dead_client.get_data_with_input,
    ):
        if hasattr(method, "retry"):
            method.retry.stop = tenacity.stop_after_attempt(1)

    with pytest.raises(aiohttp.ClientError):
        await dead_client._get_oauth_token()

    dead_client._auth_type = PolicyStoreAuth.NONE
    with pytest.raises(aiohttp.ClientError):
        await dead_client.set_policy("m.fga", "model\n  schema 1.1\ntype user\n")

    with pytest.raises(aiohttp.ClientError):
        await dead_client.set_policies(
            PolicyBundle(
                manifest=["m.fga"],
                hash="h1",
                policy_modules=[
                    RegoModule(
                        path="m.fga",
                        package_name="",
                        rego="model\n  schema 1.1\ntype user\n",
                    )
                ],
                data_modules=[],
            )
        )

    with pytest.raises(aiohttp.ClientError):
        await dead_client.get_policies()

    dead_client._parsed_policies["keep.fga"] = {
        "schema_version": "1.1",
        "type_definitions": [{"type": "user", "relations": {}}],
    }
    with pytest.raises(aiohttp.ClientError):
        await dead_client.delete_policy("other.fga")

    with pytest.raises(aiohttp.ClientError):
        await dead_client.set_policy_data({"tuples": []})

    with pytest.raises(aiohttp.ClientError):
        await dead_client.delete_policy_data("document")

    with pytest.raises(aiohttp.ClientError):
        await dead_client.patch_policy_data(
            [
                JSONPatchAction(
                    op="add",
                    path="/tuples/-",
                    value={"user": "user:a", "relation": "r", "object": "doc:1"},
                )
            ]
        )

    with pytest.raises(aiohttp.ClientError):
        await dead_client.get_data()

    with pytest.raises(aiohttp.ClientError):
        await dead_client.get_data_with_input(
            "check",
            _CheckInputModel(user="user:a", relation="r", object="doc:1"),
        )

