"""Unit + integration tests for the OpenFGA policy-store client.

The `FakeOpenFGAServer` below is a stateful, in-process implementation of the
parts of the OpenFGA HTTP API the client uses (stores, authorization models,
tuple write/read, check, healthz) - including a small authorization-model
evaluator - so the full OPAL client <-> OpenFGA flow is exercised over real
HTTP without docker.
"""

import contextlib
import io
import json
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Tuple

import aiofiles
import aiohttp
import pytest
from aiohttp import web
from opal_client.config import opal_client_config
from opal_client.policy_store.openfga_client import OpenFGAClient
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

DEMO_MODEL_FGA = """model
  schema 1.1

type user

type folder
  relations
    define owner: [user]
    define viewer: [user] or owner

type document
  relations
    define parent: [folder]
    define owner: [user] or owner from parent
    define viewer: [user] or viewer from parent
"""

DEMO_MODEL_V2_FGA = """model
  schema 1.1

type user

type folder
  relations
    define owner: [user]
    define viewer: [user] or owner

type document
  relations
    define parent: [folder]
    define owner: [user] or owner from parent
    define viewer: [user] or owner or viewer from parent
"""

FULL_BUNDLE = PolicyBundle(
    manifest=["model.fga", "data/data.json"],
    hash="commit-1",
    data_modules=[
        DataModule(
            path="data",
            data=json.dumps(
                {
                    "document:readme": {
                        "parent": ["folder:company"],
                        "viewer": ["user:anne"],
                    },
                    "folder:company": {"owner": ["user:bob"]},
                }
            ),
        )
    ],
    policy_modules=[RegoModule(path="model.fga", package_name="", rego=DEMO_MODEL_FGA)],
)

DELTA_BUNDLE = PolicyBundle(
    manifest=["model.fga"],
    hash="commit-2",
    old_hash="commit-1",
    data_modules=[],
    policy_modules=[
        RegoModule(path="model.fga", package_name="", rego=DEMO_MODEL_V2_FGA)
    ],
)


def _make_transaction(
    success: bool, transaction_type: TransactionType
) -> StoreTransaction:
    return StoreTransaction(
        id="test-id",
        actions=["set_policy_data"],
        transaction_type=transaction_type,
        success=success,
        error="" if success else "boom",
    )


@contextlib.contextmanager
def _override_config(**overrides):
    saved = {key: getattr(opal_client_config, key) for key in overrides}
    try:
        for key, value in overrides.items():
            setattr(opal_client_config, key, value)
        yield
    finally:
        for key, value in saved.items():
            setattr(opal_client_config, key, value)


@pytest.fixture(autouse=True)
def _temporary_store_backup_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        opal_client_config, "STORE_BACKUP_PATH", str(tmp_path / "backup.json")
    )


class _FakeOpenFGA:
    """Stateful fake of the OpenFGA HTTP API (enough surface for OPAL)."""

    HEALTHY = "healthy"
    ERROR = "error"  # all store-scoped requests fail with 500

    def __init__(self):
        self.mode = self.HEALTHY
        self.writes_ignored_duplicates = False
        self.fail_create_store = False
        self.fail_list_stores = False
        self.page_size_cap = None
        self.stores_page_size_cap = None
        # server state
        self._store_counter = 0
        self._stores: Dict[str, str] = {}  # id -> name
        self._models: Dict[str, List[Dict]] = {}  # store id -> [model bodies]
        self._model_ids: Dict[str, List[str]] = {}
        self._tuples: Dict[str, Dict[Tuple[str, str, str], Dict]] = {}
        # request log
        self.write_requests: List[Dict] = []
        self.authorization_model_bodies: List[Dict] = []
        self.last_auth_header: Optional[str] = None

    # -- model evaluation (a tiny Zanzibar-ish resolver) --------------------
    def _eval_relation(
        self,
        store_id: str,
        type_def: Dict,
        relation: str,
        user: str,
        object_id: str,
        depth: int = 0,
    ) -> bool:
        """Evaluates `<user> is <relation> of <object>` against the latest
        model."""
        if depth > 10:
            return False
        userset = (type_def.get("relations") or {}).get(relation)
        if userset is None:
            return False
        return self._eval_userset(
            store_id, type_def, userset, relation, user, object_id, depth
        )

    def _eval_userset(
        self,
        store_id: str,
        type_def: Dict,
        userset: Dict,
        relation: str,
        user: str,
        object_id: str,
        depth: int,
    ) -> bool:
        tuples = self._tuples.get(store_id, {})

        def has_direct(rel: str) -> bool:
            if (user, rel, object_id) in tuples:
                return True
            # a wildcard tuple (type:*) grants every user of that type
            user_type = user.split(":", 1)[0]
            return (f"{user_type}:*", rel, object_id) in tuples

        if "this" in userset:
            return has_direct(relation)
        if "computedUserset" in userset:
            target = userset["computedUserset"]["relation"]
            return self._eval_relation(
                store_id, type_def, target, user, object_id, depth + 1
            )
        if "tupleToUserset" in userset:
            ttu = userset["tupleToUserset"]
            tupleset = ttu["tupleset"]["relation"]
            computed = ttu["computedUserset"]["relation"]
            for tuple_user, tuple_relation, tuple_object in list(tuples):
                if tuple_relation == tupleset and tuple_object == object_id:
                    user_type = tuple_user.split(":", 1)[0]
                    parent_type = self._find_type(store_id, user_type)
                    if parent_type is None:
                        continue
                    if self._eval_relation(
                        store_id, parent_type, computed, user, tuple_user, depth + 1
                    ):
                        return True
            return False
        if "union" in userset:
            return any(
                self._eval_userset(
                    store_id, type_def, child, relation, user, object_id, depth + 1
                )
                for child in userset["union"]["child"]
            )
        if "intersection" in userset:
            return all(
                self._eval_userset(
                    store_id, type_def, child, relation, user, object_id, depth + 1
                )
                for child in userset["intersection"]["child"]
            )
        if "difference" in userset:
            base = self._eval_userset(
                store_id,
                type_def,
                userset["difference"]["base"],
                relation,
                user,
                object_id,
                depth + 1,
            )
            subtract = self._eval_userset(
                store_id,
                type_def,
                userset["difference"]["subtract"],
                relation,
                user,
                object_id,
                depth + 1,
            )
            return base and not subtract
        return False

    def _find_type(self, store_id: str, type_name: str) -> Optional[Dict]:
        models = self._models.get(store_id) or []
        if not models:
            return None
        for type_def in models[-1].get("type_definitions", []):
            if type_def.get("type") == type_name:
                return type_def
        return None

    def check(self, store_id: str, user: str, relation: str, object_id: str) -> bool:
        type_name = object_id.split(":", 1)[0]
        type_def = self._find_type(store_id, type_name)
        if type_def is None:
            return False
        return self._eval_relation(store_id, type_def, relation, user, object_id)

    # -- aiohttp handlers ----------------------------------------------------
    def _app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/healthz", self._handle_healthz)
        app.router.add_get("/stores", self._handle_list_stores)
        app.router.add_post("/stores", self._handle_create_store)
        app.router.add_post(
            "/stores/{store_id}/authorization-models", self._handle_write_model
        )
        app.router.add_get(
            "/stores/{store_id}/authorization-models", self._handle_list_models
        )
        app.router.add_get(
            "/stores/{store_id}/authorization-models/{model_id}", self._handle_get_model
        )
        app.router.add_post("/stores/{store_id}/write", self._handle_write)
        app.router.add_post("/stores/{store_id}/read", self._handle_read)
        app.router.add_post("/stores/{store_id}/check", self._handle_check)
        return app

    async def _guard(self, request: web.Request) -> bool:
        self.last_auth_header = request.headers.get("Authorization")
        return self.mode != self.ERROR

    async def _handle_healthz(self, request: web.Request) -> web.Response:
        if self.mode == self.ERROR:
            return web.Response(status=503, text="down")
        return web.Response(status=200, text="ok")

    async def _handle_list_stores(self, request: web.Request) -> web.Response:
        if not await self._guard(request) or self.fail_list_stores:
            return web.Response(status=500, text="down")
        stores = [{"id": sid, "name": name} for sid, name in self._stores.items()]
        page_size = self.stores_page_size_cap or len(stores)
        token = request.query.get("continuation_token")
        start = int(token) if token else 0
        page = stores[start : start + page_size]
        continuation = ""
        if start + page_size < len(stores):
            continuation = str(start + page_size)
        return web.json_response({"stores": page, "continuation_token": continuation})

    async def _handle_create_store(self, request: web.Request) -> web.Response:
        if not await self._guard(request) or self.fail_create_store:
            return web.Response(status=400, text="cannot create store")
        body = await request.json()
        for store_id, name in self._stores.items():
            if name == body.get("name"):
                return web.json_response({"error": "already exists"}, status=409)
        self._store_counter += 1
        store_id = f"S{self._store_counter}"
        self._stores[store_id] = body.get("name", "")
        self._models[store_id] = []
        self._model_ids[store_id] = []
        self._tuples[store_id] = {}
        return web.json_response({"id": store_id, "name": body.get("name")}, status=201)

    async def _handle_write_model(self, request: web.Request) -> web.Response:
        if not await self._guard(request):
            return web.Response(status=500, text="down")
        store_id = request.match_info["store_id"]
        body = await request.json()
        assert "schema_version" in body and "type_definitions" in body
        self.authorization_model_bodies.append(body)
        model_id = f"M{len(self.authorization_model_bodies)}"
        self._models.setdefault(store_id, []).append(body)
        self._model_ids.setdefault(store_id, []).append(model_id)
        return web.json_response({"authorization_model_id": model_id}, status=201)

    async def _handle_list_models(self, request: web.Request) -> web.Response:
        if not await self._guard(request):
            return web.Response(status=500, text="down")
        store_id = request.match_info["store_id"]
        return web.json_response(
            {"authorization_model_ids": self._model_ids.get(store_id, [])}
        )

    async def _handle_get_model(self, request: web.Request) -> web.Response:
        if not await self._guard(request):
            return web.Response(status=500, text="down")
        store_id = request.match_info["store_id"]
        model_id = request.match_info["model_id"]
        try:
            position = self._model_ids.get(store_id, []).index(model_id)
            return web.json_response(self._models[store_id][position])
        except (ValueError, IndexError):
            return web.json_response({"error": "not found"}, status=404)

    async def _handle_write(self, request: web.Request) -> web.Response:
        if not await self._guard(request):
            return web.Response(status=500, text="down")
        store_id = request.match_info["store_id"]
        body = await request.json()
        self.write_requests.append(body)
        tuples = self._tuples.setdefault(store_id, {})
        for key in (body.get("writes") or {}).get("tuple_keys", []):
            k = (key["user"], key["relation"], key["object"])
            if k in tuples and not self.writes_ignored_duplicates:
                if (body.get("writes") or {}).get("on_duplicate") != "ignore":
                    return web.json_response(
                        {
                            "code": "write_failed_due_to_invalid_input",
                            "message": "already exists",
                        },
                        status=400,
                    )
            tuples[k] = key.get("condition")
        for key in (body.get("deletes") or {}).get("tuple_keys", []):
            tuples.pop((key["user"], key["relation"], key["object"]), None)
        return web.json_response({}, status=200)

    async def _handle_read(self, request: web.Request) -> web.Response:
        if not await self._guard(request):
            return web.Response(status=500, text="down")
        store_id = request.match_info["store_id"]
        body = await request.json()
        tuples = self._tuples.get(store_id, {})
        key_filter = body.get("tuple_key") or {}
        results = []
        for (user, relation, object_id), condition in tuples.items():
            if key_filter.get("user") and user != key_filter["user"]:
                continue
            if key_filter.get("relation") and relation != key_filter["relation"]:
                continue
            if key_filter.get("object") and object_id != key_filter["object"]:
                continue
            key = {"user": user, "relation": relation, "object": object_id}
            if condition is not None:
                key["condition"] = condition
            results.append({"key": key, "timestamp": "2026-01-01T00:00:00Z"})
        page_size = body.get("page_size") or len(results)
        if self.page_size_cap is not None:
            page_size = min(page_size, self.page_size_cap)
        start = 0
        token = body.get("continuation_token")
        if token:
            start = int(token)
        page = results[start : start + page_size]
        continuation = ""
        if start + page_size < len(results):
            continuation = str(start + page_size)
        return web.json_response({"tuples": page, "continuation_token": continuation})

    async def _handle_check(self, request: web.Request) -> web.Response:
        if not await self._guard(request):
            return web.Response(status=500, text="down")
        store_id = request.match_info["store_id"]
        body = await request.json()
        key = body["tuple_key"]
        allowed = self.check(store_id, key["user"], key["relation"], key["object"])
        return web.json_response({"allowed": allowed})


class _ServerHandle:
    def __init__(self, fake, runner, base_url):
        self.fake = fake
        self._runner = runner
        self.base_url = base_url

    async def stop(self):
        await self._runner.cleanup()


@contextlib.asynccontextmanager
async def fake_openfga_server() -> AsyncIterator[_ServerHandle]:
    fake = _FakeOpenFGA()
    runner = web.AppRunner(fake._app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets
    port = sockets[0].getsockname()[1]
    handle = _ServerHandle(fake, runner, f"http://127.0.0.1:{port}")
    try:
        yield handle
    finally:
        await handle.stop()


def _make_client(base_url: str, **kwargs) -> OpenFGAClient:
    return OpenFGAClient(openfga_server_url=base_url, **kwargs)


class _CheckInput(BaseModel):
    user: str
    relation: str


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_flow_store_creation_model_sync_data_tuples_and_check():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            # 1. apply a full bundle: model (from .fga) + static data module
            async with client.transaction_context(
                "tx-policy", transaction_type=TransactionType.policy
            ) as tx:
                await tx.set_policies(FULL_BUNDLE)

            # store was auto-created under the configured name
            assert opal_client_config.POLICY_STORE_OPENFGA_STORE_NAME == "opal"
            assert client._store_id is not None
            version = await client.get_policy_version()
            assert version is not None

            # exactly one combined model was written, matching the transpiled DSL
            assert len(server.fake.authorization_model_bodies) == 1
            body = server.fake.authorization_model_bodies[0]
            assert body["schema_version"] == "1.1"
            assert {td["type"] for td in body["type_definitions"]} == {
                "user",
                "folder",
                "document",
            }

            # static data module was converted into tuples
            data = await client.get_data("")
            keys = {(t["user"], t["relation"], t["object"]) for t in data["tuples"]}
            assert ("user:anne", "viewer", "document:readme") in keys
            assert ("user:bob", "owner", "folder:company") in keys
            # the nested form "document:readme": {"parent": ["folder:company"]}
            # becomes a tuple whose *user* is the parent folder
            assert any(
                t["object"] == "document:readme" and t["relation"] == "parent"
                for t in data["tuples"]
            )

            # 2. external data update via a data transaction
            update = {
                "document:spec": {"viewer": ["user:carol"]},
                "folder:public": {"viewer": ["user:*"]},
            }
            async with client.transaction_context(
                "tx-data", transaction_type=TransactionType.data
            ) as tx:
                await tx.set_policy_data(update, path="/irrelevant/for/openfga")

            data = await client.get_data("")
            keys = {(t["user"], t["relation"], t["object"]) for t in data["tuples"]}
            assert ("user:carol", "viewer", "document:spec") in keys
            assert ("user:*", "viewer", "folder:public") in keys

            # 3. checks are evaluated with the real model semantics
            allowed = await client.get_data_with_input(
                "document:readme", _CheckInput(user="user:anne", relation="viewer")
            )
            assert allowed == {"allowed": True}
            # bob owns folder:company -> viewer of document:readme via 'viewer from parent'
            allowed = await client.get_data_with_input(
                "document:readme", _CheckInput(user="user:bob", relation="viewer")
            )
            assert allowed == {"allowed": True}
            allowed = await client.get_data_with_input(
                "document:readme", _CheckInput(user="user:mallory", relation="viewer")
            )
            assert allowed == {"allowed": False}

            # 4. ready/healthy after successful policy + data transactions
            assert await client.is_ready() is True
            assert await client.is_healthy() is True
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_delta_bundle_merges_into_existing_model():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            first_version = await client.get_policy_version()

            await client.set_policies(DELTA_BUNDLE)
            second_version = await client.get_policy_version()
            assert second_version != first_version

            # two models were written; the second one is the merged model
            assert len(server.fake.authorization_model_bodies) == 2
            types = {
                td["type"]
                for td in server.fake.authorization_model_bodies[1]["type_definitions"]
            }
            assert types == {"user", "folder", "document"}
            document = [
                td
                for td in server.fake.authorization_model_bodies[1]["type_definitions"]
                if td["type"] == "document"
            ][0]
            # delta introduced 'owner or viewer from parent' into the union
            viewer = document["relations"]["viewer"]
            child_usersets = viewer["union"]["child"]
            assert {"computedUserset": {"relation": "owner"}} in child_usersets
            assert any("tupleToUserset" in child for child in child_usersets)
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_single_policy_set_get_delete_and_module_ids():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)

            assert await client.get_policy_module_ids() == ["model.fga"]
            module = json.loads(await client.get_policy("model.fga"))
            assert module["schema_version"] == "1.1"
            assert await client.get_policy("missing.fga") is None
            policies = await client.get_policies()
            assert set(policies.keys()) == {"model.fga"}

            # upsert another module -> combined model re-written
            await client.set_policy(
                "extra.fga",
                "model\n  schema 1.1\n\ntype team\n  relations\n    define member: [user]\n",
            )
            assert set(await client.get_policy_module_ids()) == {
                "model.fga",
                "extra.fga",
            }
            assert len(server.fake.authorization_model_bodies) == 2

            # delete it -> another model version without the type
            await client.delete_policy("extra.fga")
            assert await client.get_policy_module_ids() == ["model.fga"]
            assert len(server.fake.authorization_model_bodies) == 3
            types = {
                td["type"]
                for td in server.fake.authorization_model_bodies[2]["type_definitions"]
            }
            assert "team" not in types
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_delete_policy_data_and_tuple_chunking():
    async with fake_openfga_server() as server:
        server.fake.writes_ignored_duplicates = True
        with _override_config(
            POLICY_STORE_OPENFGA_MAX_TUPLES_PER_WRITE=1,
            POLICY_STORE_OPENFGA_STORE_NAME="chunky",
        ):
            client = _make_client(server.base_url)
            try:
                await client.set_policies(FULL_BUNDLE)
                await client.set_policy_data(
                    {
                        "document:a": {"viewer": ["user:u1"]},
                        "document:b": {"viewer": ["user:u2"]},
                        "document:c": {"viewer": ["user:u3"]},
                    }
                )
                # 3 tuples with max 1 per write -> 3 write requests for the update
                update_writes = [
                    body for body in server.fake.write_requests if "writes" in body
                ]
                assert len(update_writes) >= 3

                # delete a single object
                await client.delete_policy_data("document:b")
                data = await client.get_data("")
                objects = {t["object"] for t in data["tuples"]}
                assert "document:b" not in objects
                assert {"document:a", "document:c", "document:readme"} <= objects

                # delete everything
                await client.delete_policy_data()
                data = await client.get_data("")
                assert data == {"tuples": []}
            finally:
                await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_store_reuse_by_name():
    async with fake_openfga_server() as server:
        client1 = _make_client(server.base_url)
        client2 = _make_client(server.base_url)
        try:
            await client1.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
            await client2.set_policy_data({"document:y": {"viewer": ["user:u2"]}})
            # both clients found/created the same named store
            assert client1._store_id == client2._store_id
        finally:
            await client1.stop_liveness_probe()
            await client2.stop_liveness_probe()


@pytest.mark.asyncio
async def test_failed_data_transaction_is_recorded_and_readiness_reported():
    """Matches the OPA/Cedar clients: failed transactions are recorded in the
    transaction log and readiness stats, while /healthy reflects the last
    *successful* transactions plus engine reachability."""
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            # production code paths (the policy/data updaters) always run
            # store writes inside transaction contexts
            async with client.transaction_context(
                "tx-policy", transaction_type=TransactionType.policy
            ) as tx:
                await tx.set_policies(FULL_BUNDLE)
            async with client.transaction_context(
                "tx-data", transaction_type=TransactionType.data
            ) as tx:
                await tx.set_policy_data({"document:z": {"viewer": ["user:u1"]}})
            assert await client.is_ready() is True
            assert await client.is_healthy() is True

            server.fake.mode = _FakeOpenFGA.ERROR
            with pytest.raises(ValueError):
                async with client.transaction_context(
                    "tx-data-2", transaction_type=TransactionType.data
                ) as tx:
                    await tx.set_policy_data({"document:z2": {"viewer": ["user:u1"]}})

            # the failed data transaction was recorded
            assert client._transaction_state._num_failed_data_transactions >= 1
            # upstream semantics: /healthy reflects the last *successful*
            # transactions, so a single failed tx does not flip it
            assert await client.is_healthy() is True

            # when the engine becomes unreachable, /healthy flips (like OPA/Cedar)
            client._set_engine_reachable(False)
            assert await client.is_healthy() is False
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_full_export_import_round_trip(tmp_path):
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            await client.set_policy_data({"document:extra": {"viewer": ["user:u9"]}})

            backup_path = tmp_path / "backup.json"
            async with aiofiles.open(backup_path, "w") as backup_file:
                await client.full_export(backup_file)

            # restore into a brand new store
            with _override_config(POLICY_STORE_OPENFGA_STORE_NAME="restored"):
                restored = _make_client(server.base_url)
                try:
                    async with aiofiles.open(backup_path, "r") as backup_file:
                        await restored.full_import(backup_file)
                    data = await restored.get_data("")
                    keys = {
                        (t["user"], t["relation"], t["object"]) for t in data["tuples"]
                    }
                    assert ("user:u9", "viewer", "document:extra") in keys
                    assert ("user:anne", "viewer", "document:readme") in keys
                finally:
                    await restored.stop_liveness_probe()
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_invalid_policy_code_raises_value_error():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            with pytest.raises(ValueError, match="invalid OpenFGA DSL"):
                await client.set_policy("bad.fga", "model\n  schema 1.1\ngarbage(")
            with pytest.raises(ValueError, match="must be .fga DSL or JSON"):
                await client.set_policy("bad.json", "{not json")
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_invalid_data_raises_value_error():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            with pytest.raises(ValueError, match="invalid data for OpenFGA store"):
                await client.set_policy_data({"nonsense": True})
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_ignored_policy_paths_skip_writes():
    async with fake_openfga_server() as server:
        with _override_config(POLICY_STORE_POLICY_PATHS_TO_IGNORE=["ignored/**"]):
            client = _make_client(server.base_url)
            try:
                await client.set_policy("ignored/skip.fga", "model\n  schema 1.1\n")
                await client.delete_policy("ignored/skip.fga")
                assert server.fake.authorization_model_bodies == []
            finally:
                await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_auth_token_sent_as_bearer_header():
    async with fake_openfga_server() as server:
        client = OpenFGAClient(
            openfga_server_url=server.base_url,
            openfga_auth_token="secret-token",
            auth_type=PolicyStoreAuth.TOKEN,
        )
        try:
            await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
            assert server.fake.last_auth_header == "Bearer secret-token"
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_client_constructor_validates_auth():
    with pytest.raises(ValueError, match="OAuth"):
        OpenFGAClient("http://localhost:8080", auth_type=PolicyStoreAuth.OAUTH)
    with pytest.raises(TypeError):
        OpenFGAClient(
            "http://localhost:8080",
            auth_type=PolicyStoreAuth.TOKEN,
            openfga_auth_token=None,
        )


def test_factory_creates_openfga_client():
    client = PolicyStoreClientFactory.create(
        store_type=PolicyStoreTypes.OPENFGA,
        url="http://localhost:8080",
        save_to_cache=False,
        data_updater_enabled=True,
        policy_updater_enabled=False,
    )
    assert isinstance(client, OpenFGAClient)
    assert client._transaction_state._policy_updater_disabled is True
    assert client._transaction_state._data_updater_disabled is False


@pytest.mark.asyncio
async def test_transaction_state_updater_flags():
    from opal_client.policy_store.openfga_client import OpenFGATransactionLogState

    state = OpenFGATransactionLogState(
        data_updater_enabled=False, policy_updater_enabled=True
    )
    assert state.ready is False  # no successful policy transaction yet
    state.process_transaction(_make_transaction(True, TransactionType.policy))
    assert state.ready is True  # data updater disabled -> not required
    assert state.healthy is True

    state.process_transaction(_make_transaction(False, TransactionType.policy))
    # upstream semantics: a failed tx does not flip healthy on its own
    assert state.healthy is True

    state.set_engine_reachable(False)
    assert state.engine_reachable is False
    assert state.healthy is False
    state.process_transaction(_make_transaction(False, TransactionType.data))
    assert state._last_failed_data_transaction is not None
    assert state._num_failed_data_transactions == 1


@pytest.mark.asyncio
async def test_connection_errors_propagate_from_write_paths():
    # a closed port produces aiohttp.ClientError, which must not be swallowed
    client = _make_client("http://127.0.0.1:1")
    try:
        with pytest.raises(aiohttp.ClientError):
            await client.set_policy("model.fga", DEMO_MODEL_FGA)
        with pytest.raises(aiohttp.ClientError):
            await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
        with pytest.raises(aiohttp.ClientError):
            await client.get_data_with_input(
                "document:x", _CheckInput(user="user:u1", relation="viewer")
            )
        # reads fail silently (matching the OPA/Cedar clients)
        assert await client.get_data("") == {"tuples": []}
    finally:
        await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_server_error_responses_raise_value_error():
    async with fake_openfga_server() as server:
        # an explicit store id skips store creation (which the fake rejects
        # in error mode) so the model/tuple error paths are exercised directly
        client = OpenFGAClient(openfga_server_url=server.base_url, store_id="S1")
        try:
            server.fake.mode = _FakeOpenFGA.ERROR
            with pytest.raises(ValueError, match="failed writing authorization model"):
                await client.set_policy("model.fga", DEMO_MODEL_FGA)
            with pytest.raises(ValueError, match="tuple write failed"):
                await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
            with pytest.raises(ValueError, match="tuple read failed"):
                await client.get_data("")
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_store_creation_failure_raises():
    async with fake_openfga_server() as server:
        server.fake.fail_create_store = True
        client = _make_client(server.base_url)
        try:
            with pytest.raises(ValueError, match="failed to create OpenFGA store"):
                await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_auto_create_disabled_requires_store_id():
    async with fake_openfga_server() as server:
        with _override_config(POLICY_STORE_OPENFGA_AUTO_CREATE_STORE=False):
            client = _make_client(server.base_url)
            try:
                with pytest.raises(ValueError, match="store id is not configured"):
                    await client.set_policy_data(
                        {"document:x": {"viewer": ["user:u1"]}}
                    )
            finally:
                await client.stop_liveness_probe()
        # with an explicit store id everything works even with auto-create off
        with _override_config(POLICY_STORE_OPENFGA_AUTO_CREATE_STORE=False):
            client = OpenFGAClient(openfga_server_url=server.base_url, store_id="S77")
            try:
                await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
                assert await client._ensure_store_id() == "S77"
            finally:
                await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_patch_policy_data_treated_as_upsert():
    async with fake_openfga_server() as server:
        server.fake.writes_ignored_duplicates = True
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            await client.patch_policy_data(
                {"document:readme": {"viewer": ["user:newcomer"]}}
            )
            data = await client.get_data("document:readme")
            users = {t["user"] for t in data["tuples"]}
            assert "user:newcomer" in users
            assert "user:anne" in users  # existing tuples are untouched
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_empty_data_update_is_noop():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            writes_before = len(server.fake.write_requests)
            await client.set_policy_data({"tuples": []})
            assert len(server.fake.write_requests) == writes_before
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_delete_unknown_policy_module_is_noop():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            bodies_before = len(server.fake.authorization_model_bodies)
            await client.delete_policy("missing.fga")
            assert len(server.fake.authorization_model_bodies) == bodies_before
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_delta_bundle_with_deleted_modules_and_bad_data_module():
    deleted = PolicyBundle(
        manifest=[],
        hash="commit-3",
        old_hash="commit-2",
        data_modules=[DataModule(path="data", data="!! not json !!")],
        policy_modules=[],
        deleted_files=DeletedFiles(policy_modules=[Path("model.fga")]),
    )
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            await client.set_policies(DELTA_BUNDLE)
            # the delta deletes model.fga and ships a non-json data module
            # (which must be skipped with a warning, not crash the update)
            await client.set_policies(deleted)
            assert await client.get_policy_module_ids() == []
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_cached_tuples_are_upserted_and_backed_up(tmp_path):
    async with fake_openfga_server() as server:
        server.fake.writes_ignored_duplicates = True
        client = _make_client(server.base_url, cache_policy_data=True)
        try:
            await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
            # same key, different tuple -> upserted in the cache
            await client.set_policy_data({"document:x": {"viewer": ["user:u2"]}})
            await client.delete_policy_data("document:x")

            backup_path = tmp_path / "backup.json"
            async with aiofiles.open(backup_path, "w") as backup_file:
                await client.full_export(backup_file)
            async with aiofiles.open(backup_path, "r") as backup_file:
                backup = json.loads(await backup_file.read())
            assert backup["tuples"] == []
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_read_pagination_follows_continuation_tokens():
    async with fake_openfga_server() as server:
        server.fake.page_size_cap = 1
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            await client.set_policy_data(
                {
                    "document:a": {"viewer": ["user:u1"]},
                    "document:b": {"viewer": ["user:u2"]},
                }
            )
            data = await client.get_data("")
            # page size capped at 1 -> multiple reads, all tuples returned
            assert len(data["tuples"]) >= 4
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_get_data_with_input_validation_and_extras():
    class FullInput(BaseModel):
        user: str
        relation: str
        context: dict
        contextual_tuples: list

    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            with pytest.raises(ValueError, match="expects input"):
                await client.get_data_with_input(
                    "document:x", _CheckInput(user="user:u1", relation="")
                )

            allowed = await client.get_data_with_input(
                "/document:readme",
                FullInput(
                    user="user:anne",
                    relation="viewer",
                    context={},
                    contextual_tuples=[
                        {
                            "user": "user:anne",
                            "relation": "viewer",
                            "object": "document:readme",
                        }
                    ],
                ),
            )
            assert allowed == {"allowed": True}
        finally:
            await client.stop_liveness_probe()


EXTRA_MODEL_FGA = """model
  schema 1.1

type team
  relations
    define member: [user]
"""

TWO_MODULE_BUNDLE = PolicyBundle(
    manifest=["model.fga", "team.fga"],
    hash="commit-two-modules",
    data_modules=[],
    policy_modules=[
        RegoModule(path="model.fga", package_name="", rego=DEMO_MODEL_FGA),
        RegoModule(path="team.fga", package_name="", rego=EXTRA_MODEL_FGA),
    ],
)

TWO_MODULE_DELTA = PolicyBundle(
    manifest=["model.fga"],
    hash="commit-two-modules-v2",
    old_hash="commit-two-modules",
    data_modules=[],
    policy_modules=[
        RegoModule(path="model.fga", package_name="", rego=DEMO_MODEL_V2_FGA)
    ],
)


@pytest.mark.asyncio
async def test_restart_delta_preserves_unchanged_modules():
    async with fake_openfga_server() as server:
        first = _make_client(server.base_url)
        try:
            await first.set_policies(TWO_MODULE_BUNDLE)
        finally:
            await first.stop_liveness_probe()

        second = _make_client(server.base_url)
        try:
            assert set(await second.get_policy_module_ids()) == {
                "model.fga",
                "team.fga",
            }
            await second.set_policies(TWO_MODULE_DELTA)
            body = server.fake.authorization_model_bodies[-1]
            assert {item["type"] for item in body["type_definitions"]} == {
                "user",
                "folder",
                "document",
                "team",
            }
        finally:
            await second.stop_liveness_probe()


@pytest.mark.asyncio
async def test_restart_delta_reconstructs_an_existing_store_without_sidecar():
    async with fake_openfga_server() as server:
        first = _make_client(server.base_url)
        try:
            await first.set_policies(TWO_MODULE_BUNDLE)
            state_path = first._module_state_path
        finally:
            await first.stop_liveness_probe()
        state_path = Path(state_path)
        state_path.unlink()

        second = _make_client(server.base_url)
        try:
            await second.set_policies(TWO_MODULE_DELTA)
            body = server.fake.authorization_model_bodies[-1]
            assert {item["type"] for item in body["type_definitions"]} == {
                "user",
                "folder",
                "document",
                "team",
            }
        finally:
            await second.stop_liveness_probe()


@pytest.mark.asyncio
async def test_invalid_sidecar_falls_back_to_store_reconstruction():
    async with fake_openfga_server() as server:
        first = _make_client(server.base_url)
        try:
            await first.set_policies(TWO_MODULE_BUNDLE)
            state_path = Path(first._module_state_path)
        finally:
            await first.stop_liveness_probe()
        state_path.write_text("{invalid", encoding="utf-8")

        second = _make_client(server.base_url)
        try:
            await second.set_policies(TWO_MODULE_DELTA)
            body = server.fake.authorization_model_bodies[-1]
            assert {item["type"] for item in body["type_definitions"]} == {
                "user",
                "folder",
                "document",
                "team",
            }
        finally:
            await second.stop_liveness_probe()


@pytest.mark.asyncio
async def test_deleted_data_module_removes_only_its_tuples():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            await client.set_policy_data(
                {"document:external": {"viewer": ["user:ext"]}}
            )
            delta = PolicyBundle(
                manifest=[],
                hash="commit-data-delete",
                old_hash="commit-1",
                data_modules=[],
                policy_modules=[],
                deleted_files=DeletedFiles(data_modules=[Path("data")]),
            )
            await client.set_policies(delta)
            keys = {
                (tuple_data["user"], tuple_data["relation"], tuple_data["object"])
                for tuple_data in (await client.get_data(""))["tuples"]
            }
            assert ("user:anne", "viewer", "document:readme") not in keys
            assert ("user:ext", "viewer", "document:external") in keys
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_full_import_replaces_owned_state_and_preserves_unrelated_tuples(
    tmp_path,
):
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            await client.set_policy_data(
                {"document:before": {"viewer": ["user:before"]}}
            )
            store_id = client._store_id
            server.fake._tuples[store_id][
                ("user:outside", "viewer", "document:outside")
            ] = None
            backup_path = tmp_path / "replacement.json"
            async with aiofiles.open(backup_path, "w") as backup_file:
                await client.full_export(backup_file)
            await client.set_policy_data({"document:after": {"viewer": ["user:after"]}})

            async with aiofiles.open(backup_path, "r") as backup_file:
                await client.full_import(backup_file)

            keys = {
                (tuple_data["user"], tuple_data["relation"], tuple_data["object"])
                for tuple_data in (await client.get_data(""))["tuples"]
            }
            assert ("user:before", "viewer", "document:before") in keys
            assert ("user:after", "viewer", "document:after") not in keys
            assert ("user:outside", "viewer", "document:outside") in keys
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_deleting_the_final_policy_module_clears_managed_state():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            await client.delete_policy("model.fga")
            assert await client.get_policy_module_ids() == []
            assert await client.get_policy_version() is None
            assert (await client.get_data(""))["tuples"] == []
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_ordinary_policy_update_preserves_other_modules():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(TWO_MODULE_BUNDLE)
            await client.set_policy("team.fga", EXTRA_MODEL_FGA)
            assert set(await client.get_policy_module_ids()) == {
                "model.fga",
                "team.fga",
            }
            body = server.fake.authorization_model_bodies[-1]
            assert {item["type"] for item in body["type_definitions"]} == {
                "user",
                "folder",
                "document",
                "team",
            }
        finally:
            await client.stop_liveness_probe()


CONDITION_MODEL_FGA = """model
  schema 1.1

type user

type document
  relations
    define viewer: [user with non_expired_grant]
  condition non_expired_grant(current_time: timestamp, grant_expires_at: timestamp) {
    current_time < grant_expires_at
  }
"""


CONDITION_BUNDLE = PolicyBundle(
    manifest=["model.fga"],
    hash="commit-cond",
    data_modules=[],
    policy_modules=[
        RegoModule(path="model.fga", package_name="", rego=CONDITION_MODEL_FGA)
    ],
)


@pytest.mark.asyncio
async def test_combined_model_with_conditions_is_written():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(CONDITION_BUNDLE)
            body = server.fake.authorization_model_bodies[-1]
            # the transpiled condition was carried over to the written model
            assert "conditions" in body
            assert "non_expired_grant" in body["conditions"]
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_store_reuse_follows_paginated_store_listing():
    async with fake_openfga_server() as server:
        # two pre-existing stores; the fake pages its /stores listing at 1
        # per page, so finding the existing store requires continuation tokens
        server.fake._store_counter = 2
        server.fake._stores = {"S1": "someone-elses", "S2": "opal"}
        server.fake.stores_page_size_cap = 1
        client = _make_client(server.base_url)
        try:
            # no store id configured -> creating "opal" conflicts (409), so
            # the client looks the store up by name across the paginated
            # listing instead
            await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
            assert client._store_id == "S2"
            assert await client._ensure_store_id() == "S2"
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_store_lookup_failure_after_name_conflict_raises():
    async with fake_openfga_server() as server:
        server.fake._store_counter = 1
        server.fake._stores = {"S1": "opal"}
        server.fake.fail_list_stores = True
        client = _make_client(server.base_url)
        try:
            # store creation conflicts with the existing name, and the
            # fallback listing fails -> the client must raise
            with pytest.raises(ValueError, match="failed to list OpenFGA stores"):
                await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_connection_errors_with_explicit_store_id_propagate():
    # with a pre-configured store id, no store provisioning is attempted, so
    # every request path itself is what fails with aiohttp.ClientError
    client = OpenFGAClient(openfga_server_url="http://127.0.0.1:1", store_id="S1")
    try:
        assert await client._ensure_store_id() == "S1"
        with pytest.raises(aiohttp.ClientError):
            await client.set_policy("model.fga", DEMO_MODEL_FGA)
        with pytest.raises(aiohttp.ClientError):
            await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
        with pytest.raises(aiohttp.ClientError):
            await client.get_data_with_input(
                "document:x", _CheckInput(user="user:u1", relation="viewer")
            )
        # get_data fails silently (like the OPA/Cedar clients)
        assert await client.get_data("") == {"tuples": []}
    finally:
        await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_check_error_response_raises_value_error():
    async with fake_openfga_server() as server:
        client = OpenFGAClient(openfga_server_url=server.base_url, store_id="S1")
        try:
            server.fake.mode = _FakeOpenFGA.ERROR
            with pytest.raises(ValueError, match="check failed"):
                await client.get_data_with_input(
                    "document:x", _CheckInput(user="user:u1", relation="viewer")
                )
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_delete_policy_data_without_matches_is_noop():
    async with fake_openfga_server() as server:
        client = _make_client(server.base_url)
        try:
            await client.set_policies(FULL_BUNDLE)
            writes_before = len(server.fake.write_requests)
            # no tuple matches this path -> nothing is read/written
            await client.delete_policy_data("document:missing")
            assert len(server.fake.write_requests) == writes_before
        finally:
            await client.stop_liveness_probe()


@pytest.mark.asyncio
async def test_cached_tuple_rewritten_in_place(tmp_path):
    async with fake_openfga_server() as server:
        server.fake.writes_ignored_duplicates = True
        client = _make_client(server.base_url, cache_policy_data=True)
        try:
            await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
            # exact same tuple again -> the cached copy is updated in place
            # (not duplicated), and the server ignores the duplicate
            await client.set_policy_data({"document:x": {"viewer": ["user:u1"]}})
            assert len(client._policy_data_cache) == 1

            backup_path = tmp_path / "backup.json"
            async with aiofiles.open(backup_path, "w") as backup_file:
                await client.full_export(backup_file)
            async with aiofiles.open(backup_path, "r") as backup_file:
                backup = json.loads(await backup_file.read())
            assert len(backup["tuples"]) == 1
        finally:
            await client.stop_liveness_probe()
