"""OpenFGA policy-store client.

OpenFGA (https://openfga.dev) is a fine-grained authorization engine based
on Google's Zanzibar. Unlike OPA/Cedar, OpenFGA does not store independently
addressable "policy files"; a store holds one *authorization model* (versioned
and immutable) plus relationship *tuples* (the data). This client maps OPAL's
policy/data concepts onto OpenFGA as follows:

- Policy sync: every policy module in a bundle (a `.fga` DSL file or a JSON
  model fragment) is compiled into a single *combined authorization model*
  which is written once per update (POST /stores/{id}/authorization-models).
  Modules are kept in memory so delta bundles (or direct set_policy/delete_policy
  calls) modify the combined model and write a new immutable version.
- Data sync: OPAL data updates are converted into relationship tuples
  (see `openfga_tuples.convert_to_tuples`) and written via POST /stores/{id}/write.
  Data deletions read the affected tuples and write them as deletes.
- `get_data_with_input` maps onto OpenFGA's Check API.

If no store id is configured (POLICY_STORE_OPENFGA_STORE_ID), a store named
POLICY_STORE_OPENFGA_STORE_NAME is created (or looked up by name) on first use.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

import aiohttp
from aiofiles.threadpool.text import AsyncTextIOWrapper
from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_client.policy_store.base_policy_store_client import (
    BasePolicyStoreClient,
    JsonableValue,
)
from opal_client.policy_store.liveness_probe import LivenessProbeMixin
from opal_client.policy_store.opa_client import (
    RETRY_CONFIG,
    affects_transaction,
    fail_silently,
    should_ignore_path,
)
from opal_client.policy_store.openfga_dsl import (
    OpenFGADslError,
    merge_models,
    normalize_model,
    strip_extend,
    transpile_fga_to_model,
)
from opal_client.policy_store.openfga_tuples import (
    TupleConversionError,
    convert_to_tuples,
    filter_tuples_by_object_prefix,
)
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.store import StoreTransaction, TransactionType
from pydantic import BaseModel
from tenacity import retry


class OpenFGATransactionLogState:
    """In-memory transaction/health state (mirrors the OPA client semantics).

    The state honors disabled updaters (unlike the Cedar client): a disabled
    updater can never fail, so it must not render the store not-ready.
    """

    def __init__(
        self,
        data_updater_enabled: bool = True,
        policy_updater_enabled: bool = True,
    ):
        self._data_updater_disabled = not data_updater_enabled
        self._policy_updater_disabled = not policy_updater_enabled
        self._num_successful_policy_transactions = 0
        self._num_failed_policy_transactions = 0
        self._num_successful_data_transactions = 0
        self._num_failed_data_transactions = 0
        self._last_policy_transaction: Optional[StoreTransaction] = None
        self._last_failed_policy_transaction: Optional[StoreTransaction] = None
        self._last_data_transaction: Optional[StoreTransaction] = None
        self._last_failed_data_transaction: Optional[StoreTransaction] = None
        # Live reachability of the OpenFGA server, maintained by the
        # background liveness probe (see LivenessProbeMixin).
        self._engine_reachable: bool = True

    @property
    def engine_reachable(self) -> bool:
        return self._engine_reachable

    def set_engine_reachable(self, value: bool) -> None:
        self._engine_reachable = value

    @property
    def ready(self) -> bool:
        policy_ready = (
            self._policy_updater_disabled
            or self._num_successful_policy_transactions > 0
        )
        data_ready = (
            self._data_updater_disabled or self._num_successful_data_transactions > 0
        )
        return policy_ready and data_ready

    @property
    def healthy(self) -> bool:
        policy_healthy = self._policy_updater_disabled or (
            self._last_policy_transaction is not None
            and self._last_policy_transaction.success
        )
        data_healthy = self._data_updater_disabled or (
            self._last_data_transaction is not None
            and self._last_data_transaction.success
        )
        transactions_healthy = policy_healthy and data_healthy
        is_healthy = transactions_healthy and self._engine_reachable
        logger.debug(
            f"OpenFGA client health: {is_healthy} (policy: {policy_healthy}, "
            f"data: {data_healthy}, engine_reachable: {self._engine_reachable})"
        )
        return is_healthy

    def process_transaction(self, transaction: StoreTransaction):
        if transaction.transaction_type == TransactionType.policy:
            if transaction.success:
                self._last_policy_transaction = transaction
                self._num_successful_policy_transactions += 1
            else:
                self._last_failed_policy_transaction = transaction
                self._num_failed_policy_transactions += 1
        elif transaction.transaction_type == TransactionType.data:
            if transaction.success:
                self._last_data_transaction = transaction
                self._num_successful_data_transactions += 1
            else:
                self._last_failed_data_transaction = transaction
                self._num_failed_data_transactions += 1


class OpenFGAClient(LivenessProbeMixin, BasePolicyStoreClient):
    """An OPAL policy-store client for OpenFGA (https://openfga.dev)."""

    def __init__(
        self,
        openfga_server_url: str = None,
        openfga_auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        store_id: Optional[str] = None,
        data_updater_enabled: bool = True,
        policy_updater_enabled: bool = True,
        cache_policy_data: bool = False,
    ):
        base_url = openfga_server_url or opal_client_config.POLICY_STORE_URL
        self._openfga_url = base_url.rstrip("/")
        self._token = openfga_auth_token
        self._auth_type: PolicyStoreAuth = auth_type

        # store bootstrap: a store id may be given explicitly, read from
        # confi, or auto-provisioned by name on first use.
        self._store_id: Optional[str] = (
            store_id or opal_client_config.POLICY_STORE_OPENFGA_STORE_ID
        )
        self._store_name: str = opal_client_config.POLICY_STORE_OPENFGA_STORE_NAME
        self._auto_create_store: bool = (
            opal_client_config.POLICY_STORE_OPENFGA_AUTO_CREATE_STORE
        )
        self._store_lock = asyncio.Lock()

        # optional authorization-model pinning for tuple writes/checks
        self._pinned_model_id: Optional[
            str
        ] = opal_client_config.POLICY_STORE_OPENFGA_AUTHORIZATION_MODEL_ID
        self._max_tuples_per_write: int = max(
            1, opal_client_config.POLICY_STORE_OPENFGA_MAX_TUPLES_PER_WRITE
        )
        self._ignore_duplicate_tuples: bool = (
            opal_client_config.POLICY_STORE_OPENFGA_IGNORE_DUPLICATE_TUPLES
        )

        # in-memory policy state: policy_id (module path) -> normalized model
        # fragment; combined into a single authorization model on every write.
        self._modules: Dict[str, Dict] = {}
        self._model_lock = asyncio.Lock()
        self._policy_version: Optional[str] = None

        # optional in-memory cache of written tuples (offline/backup mode)
        self._policy_data_cache: Optional[List[Dict]] = (
            [] if cache_policy_data else None
        )

        self._transaction_state = OpenFGATransactionLogState(
            data_updater_enabled=data_updater_enabled,
            policy_updater_enabled=policy_updater_enabled,
        )

        self._engine_reachable: bool = True
        self._init_liveness_probe()

        if auth_type == PolicyStoreAuth.OAUTH:
            raise ValueError("OpenFGA client does not support OAuth.")
        if auth_type == PolicyStoreAuth.TOKEN and not self._token:
            logger.error("POLICY_STORE_AUTH_TOKEN can not be empty")
            raise TypeError("required variables for token auth are not set")

        logger.info(f"Authentication mode for policy store: {auth_type}")

    # ------------------------------------------------------------------
    # urls / auth
    # ------------------------------------------------------------------

    def _store_url(self, suffix: str = "") -> str:
        return f"{self._openfga_url}/stores/{self._store_id}{suffix}"

    def _get_auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._auth_type == PolicyStoreAuth.TOKEN and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    # ------------------------------------------------------------------
    # store bootstrap
    # ------------------------------------------------------------------

    async def _ensure_store_id(self) -> str:
        """Returns the configured store id, creating/looking up a store by
        name when none was configured (OpenFGA ids are server generated)."""
        if self._store_id:
            return self._store_id
        async with self._store_lock:
            if not self._store_id:
                self._store_id = await self._provision_store()
            return self._store_id

    async def _provision_store(self) -> str:
        if not self._auto_create_store:
            raise ValueError(
                "OpenFGA store id is not configured: set "
                "POLICY_STORE_OPENFGA_STORE_ID or enable "
                "POLICY_STORE_OPENFGA_AUTO_CREATE_STORE"
            )
        async with aiohttp.ClientSession(trust_env=True) as session:
            response = await session.post(
                f"{self._openfga_url}/stores",
                json={"name": self._store_name},
                headers=self._get_auth_headers(),
            )
            if response.status == 201:
                result = await response.json()
                logger.info(
                    "Created OpenFGA store {name!r} with id {id}",
                    name=self._store_name,
                    id=result["id"],
                )
                return result["id"]
            # store may already exist (conflict) - look it up by name
            stores = await self._list_stores(session)
            for store in stores:
                if store.get("name") == self._store_name:
                    logger.info(
                        "Reusing existing OpenFGA store {name!r} with id {id}",
                        name=self._store_name,
                        id=store["id"],
                    )
                    return store["id"]
            raise ValueError(
                f"failed to create OpenFGA store {self._store_name!r}: "
                f"HTTP {response.status}: {await response.text()}"
            )

    async def _list_stores(self, session: aiohttp.ClientSession) -> List[Dict]:
        stores: List[Dict] = []
        continuation_token = ""
        while True:
            params: Dict[str, Any] = {"page_size": 100}
            if continuation_token:
                params["continuation_token"] = continuation_token
            async with session.get(
                f"{self._openfga_url}/stores",
                params=params,
                headers=self._get_auth_headers(),
            ) as response:
                if response.status != 200:
                    raise ValueError(
                        f"failed to list OpenFGA stores: HTTP {response.status}"
                    )
                result = await response.json()
            stores.extend(result.get("stores", []))
            continuation_token = result.get("continuation_token") or ""
            if not continuation_token:
                return stores

    # ------------------------------------------------------------------
    # policy (authorization model) management
    # ------------------------------------------------------------------

    def _parse_policy_code(self, policy_id: str, policy_code: str) -> Dict:
        """Parses a policy module's contents (DSL or JSON) into a normalized
        model fragment."""
        if policy_id.endswith(".fga"):
            try:
                return normalize_model(transpile_fga_to_model(policy_code))
            except OpenFGADslError as err:
                logger.error(
                    "OpenFGA policy module {id} is not valid OpenFGA DSL: {err}",
                    id=policy_id,
                    err=repr(err),
                )
                raise ValueError(f"invalid OpenFGA DSL in {policy_id}: {err}")
        # JSON module: a full model, {"type_definitions": [...]}, or a bare
        # list of type definitions
        try:
            return normalize_model(json.loads(policy_code))
        except json.JSONDecodeError as err:
            logger.error(
                "OpenFGA policy module {id} is not valid JSON or DSL: {err}",
                id=policy_id,
                err=repr(err),
            )
            raise ValueError(
                f"OpenFGA policy module {policy_id} must be .fga DSL or JSON: {err}"
            )

    async def _write_combined_model(self) -> Optional[str]:
        """Merges all tracked modules into one authorization model and writes
        it to OpenFGA. Returns the new authorization model id (or None when
        there is nothing to write)."""
        if not self._modules:
            return None
        model = strip_extend(merge_models(list(self._modules.values())))
        body: Dict[str, Any] = {
            "schema_version": model["schema_version"],
            "type_definitions": model["type_definitions"],
        }
        if model.get("conditions"):
            body["conditions"] = model["conditions"]

        store_id = await self._ensure_store_id()
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                async with session.post(
                    self._store_url("/authorization-models"),
                    json=body,
                    headers=self._get_auth_headers(),
                ) as response:
                    if response.status != 201:
                        error = await response.text()
                        raise ValueError(
                            f"OpenFGA Client: failed writing authorization model: "
                            f"HTTP {response.status}, error: {error}"
                        )
                    result = await response.json()
                model_id = result["authorization_model_id"]
                logger.info(
                    "Wrote combined OpenFGA authorization model {id} "
                    "({n} modules, {t} type definitions)",
                    id=model_id,
                    n=len(self._modules),
                    t=len(body["type_definitions"]),
                )
                return model_id
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG, reraise=True)
    async def set_policy(
        self,
        policy_id: str,
        policy_code: str,
        transaction_id: Optional[str] = None,
    ):
        """Upserts a single policy module and rewrites the combined model."""
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring setting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return
        async with self._model_lock:
            self._modules[policy_id] = self._parse_policy_code(policy_id, policy_code)
            model_id = await self._write_combined_model()
            if model_id is not None:
                self._policy_version = model_id

    @affects_transaction
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        """Applies a policy bundle (full or delta) to the store.

        Each policy module in the bundle is parsed (OpenFGA DSL or JSON) and
        merged into the in-memory combined model, which is then written to
        OpenFGA as a new immutable authorization-model version. Static data
        modules bundled in the policy repo are converted into tuples.
        """
        async with self._model_lock:
            if bundle.old_hash is None:
                # a complete bundle replaces the previous state
                self._modules = {}

            deleted_modules: List[str] = []
            if bundle.old_hash is not None and bundle.deleted_files is not None:
                deleted_modules = [
                    str(module) for module in bundle.deleted_files.policy_modules
                ]
            for module_id in deleted_modules:
                self._modules.pop(str(module_id), None)

            for policy in bundle.policy_modules:
                self._modules[policy.path] = self._parse_policy_code(
                    policy.path, policy.rego
                )

            model_id = await self._write_combined_model()
            if model_id is not None:
                self._policy_version = model_id
            if deleted_modules:
                logger.warning(
                    "OpenFGA authorization models are immutable - deleted "
                    "policy modules {modules} were removed from the combined "
                    "model, which was re-written as a new version",
                    modules=deleted_modules,
                )

        # data modules (e.g. static tuples checked into the policy repo)
        for module in bundle.data_modules:
            try:
                module_data = json.loads(module.data)
            except json.JSONDecodeError as err:
                logger.warning(
                    "bundle contains non-json data module: {module_path}",
                    module_path=module.path,
                    err=repr(err),
                )
                continue
            await self.set_policy_data(module_data, path=module.path)

        logger.debug("OpenFGA set_policies done, bundle hash {hash}", hash=bundle.hash)

    @fail_silently()
    @retry(**RETRY_CONFIG, reraise=True)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        """Returns a policy module's normalized model fragment as JSON."""
        async with self._model_lock:
            module = self._modules.get(policy_id)
        if module is None:
            return None
        return json.dumps(module)

    @fail_silently()
    @retry(**RETRY_CONFIG, reraise=True)
    async def get_policies(self) -> Optional[Dict[str, str]]:
        async with self._model_lock:
            return {path: json.dumps(module) for path, module in self._modules.items()}

    async def get_policy_module_ids(self) -> List[str]:
        async with self._model_lock:
            return list(self._modules.keys())

    @affects_transaction
    @retry(**RETRY_CONFIG, reraise=True)
    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        """Removes a module from the in-memory combined model and rewrites it.

        OpenFGA authorization models are immutable, so "deleting" a policy
        means writing a new model version without the module's definitions.
        """
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring deleting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return
        async with self._model_lock:
            if policy_id not in self._modules:
                logger.warning(
                    "attempted to delete unknown OpenFGA policy module {id}",
                    id=policy_id,
                )
                return
            del self._modules[policy_id]
            model_id = await self._write_combined_model()
            if model_id is not None:
                self._policy_version = model_id

    async def get_policy_version(self) -> Optional[str]:
        """The id of the latest authorization model written to the store."""
        return self._policy_version

    # ------------------------------------------------------------------
    # data (relationship tuples) management
    # ------------------------------------------------------------------

    @affects_transaction
    @retry(**RETRY_CONFIG, reraise=True)
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        """Writes data updates into OpenFGA as relationship tuples.

        `policy_data` is converted by `openfga_tuples.convert_to_tuples`
        (tuple-native shapes and a nested object->relation->users form are
        supported). `path` is accepted for interface compatibility (OPAL data
        paths do not exist in OpenFGA); it is ignored for writes.
        """
        if path:
            logger.warning(
                "OpenFGA has no data paths - ignoring dst_path {path!r} for "
                "this data update (tuples carry their own object ids)",
                path=path,
            )
        try:
            tuples = convert_to_tuples(policy_data)
        except TupleConversionError as err:
            logger.error(
                "Failed converting data update to OpenFGA tuples: {err}",
                err=repr(err),
            )
            raise ValueError(f"invalid data for OpenFGA store: {err}")
        if not tuples:
            logger.info("Data update contained no tuples; nothing to write")
            return

        for chunk in _chunks(tuples, self._max_tuples_per_write):
            await self._write_tuples(writes=chunk)

        if self._policy_data_cache is not None:
            self._policy_data_cache = _upsert_tuples(self._policy_data_cache, tuples)

    @affects_transaction
    @retry(**RETRY_CONFIG, reraise=True)
    async def patch_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        """PATCH is treated like an upsert write (OpenFGA tuple writes are
        idempotent with `on_duplicate: ignore`)."""
        await self.set_policy_data(policy_data, path=path)

    @affects_transaction
    @retry(**RETRY_CONFIG, reraise=True)
    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        """Deletes relationship tuples from OpenFGA.

        OpenFGA cannot delete "by path"; the tuples to delete are read first
        (filtered by object prefix when `path` is given) and then deleted
        explicitly. An empty path deletes *all* tuples in the store.
        """
        # an exact object path ("type:id") can be filtered server-side;
        # prefix paths are filtered client-side below
        object_filter = path if ":" in path else ""
        existing = await self._read_all_tuples(object_filter=object_filter)
        existing = filter_tuples_by_object_prefix(existing, path)
        if not existing:
            logger.info("No tuples matched path {path!r}; nothing to delete", path=path)
            return
        delete_keys = [
            {"user": t["user"], "relation": t["relation"], "object": t["object"]}
            for t in existing
        ]
        for chunk in _chunks(delete_keys, self._max_tuples_per_write):
            await self._write_tuples(deletes=chunk)

        if self._policy_data_cache is not None:
            self._policy_data_cache = [
                t
                for t in self._policy_data_cache
                if (t["user"], t["relation"], t["object"])
                not in {(d["user"], d["relation"], d["object"]) for d in delete_keys}
            ]

    @fail_silently(fallback={"tuples": []})
    @retry(**RETRY_CONFIG, reraise=True)
    async def get_data(self, path: str) -> Dict:
        """Returns relationship tuples as {"tuples": [...]} (flat write-shaped
        tuples). When `path` is given, only tuples whose object matches the
        path (exact match or prefix) are returned."""
        tuples = await self._read_all_tuples(object_filter=path)
        tuples = filter_tuples_by_object_prefix(tuples, path)
        return {"tuples": tuples}

    @retry(**RETRY_CONFIG, reraise=True)
    async def get_data_with_input(self, path: str, input: BaseModel) -> Dict:
        """Maps onto OpenFGA's Check API.

        `path` is the object to check ("type:id"); `input` must carry at least
        a "user" and a "relation" (plus an optional "context" object and
        "contextual_tuples"). Returns {"allowed": bool}.
        """
        payload = input.dict()
        user = payload.get("user")
        relation = payload.get("relation")
        if not user or not relation:
            raise ValueError(
                "OpenFGA get_data_with_input expects input with 'user' and 'relation'"
            )
        body: Dict[str, Any] = {
            "tuple_key": {
                "user": user,
                "relation": relation,
                "object": path.lstrip("/"),
            }
        }
        if payload.get("context") is not None:
            body["context"] = payload["context"]
        if payload.get("contextual_tuples"):
            body["contextual_tuples"] = {"tuple_keys": payload["contextual_tuples"]}
        model_id = self._policy_version or self._pinned_model_id
        if model_id:
            body["authorization_model_id"] = model_id

        store_id = await self._ensure_store_id()
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                async with session.post(
                    self._store_url("/check"),
                    json=body,
                    headers=self._get_auth_headers(),
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        raise ValueError(
                            f"OpenFGA Client: check failed: HTTP {response.status}, "
                            f"error: {error}"
                        )
                    result = await response.json()
                return {"allowed": bool(result.get("allowed", False))}
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    async def _write_tuples(
        self, writes: Optional[List[Dict]] = None, deletes: Optional[List[Dict]] = None
    ) -> None:
        """Issues one /write request with the given tuple writes/deletes."""
        body: Dict[str, Any] = {}
        if writes:
            writes_body: Dict[str, Any] = {"tuple_keys": writes}
            if self._ignore_duplicate_tuples:
                writes_body["on_duplicate"] = "ignore"
            body["writes"] = writes_body
        if deletes:
            deletes_body: Dict[str, Any] = {"tuple_keys": deletes}
            body["deletes"] = deletes_body

        model_id = self._policy_version or self._pinned_model_id
        if model_id:
            body["authorization_model_id"] = model_id

        store_id = await self._ensure_store_id()
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                async with session.post(
                    self._store_url("/write"),
                    json=body,
                    headers=self._get_auth_headers(),
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        raise ValueError(
                            f"OpenFGA Client: tuple write failed: HTTP {response.status}, "
                            f"error: {error}"
                        )
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    async def _read_all_tuples(self, object_filter: str = "") -> List[Dict]:
        """Pages through POST /read and returns flat write-shaped tuples.

        When `object_filter` is a full object id ("type:id") it is sent as the
        server-side tuple_key filter.
        """
        tuples: List[Dict] = []
        continuation_token = ""
        store_id = await self._ensure_store_id()
        headers = self._get_auth_headers()
        async with aiohttp.ClientSession(trust_env=True) as session:
            while True:
                body: Dict[str, Any] = {"page_size": 100}
                if object_filter:
                    body["tuple_key"] = {"object": object_filter}
                if continuation_token:
                    body["continuation_token"] = continuation_token
                try:
                    async with session.post(
                        self._store_url("/read"),
                        json=body,
                        headers=headers,
                    ) as response:
                        if response.status != 200:
                            error = await response.text()
                            raise ValueError(
                                f"OpenFGA Client: tuple read failed: "
                                f"HTTP {response.status}, error: {error}"
                            )
                        result = await response.json()
                except aiohttp.ClientError as e:
                    logger.warning("OpenFGA connection error: {err}", err=repr(e))
                    raise
                tuples.extend(_flatten_tuples(result.get("tuples", [])))
                continuation_token = result.get("continuation_token") or ""
                if not continuation_token:
                    return tuples

    # ------------------------------------------------------------------
    # transactions / health
    # ------------------------------------------------------------------

    async def log_transaction(self, transaction: StoreTransaction):
        self._transaction_state.process_transaction(transaction)

    async def is_ready(self) -> bool:
        return self._transaction_state.ready

    async def is_healthy(self) -> bool:
        return self._transaction_state.healthy

    @property
    def _probe_log_label(self) -> str:
        return "OpenFGA"

    async def _probe_engine_reachable(self, session: aiohttp.ClientSession) -> bool:
        """Probes the OpenFGA server's health endpoint (/healthz, which the
        server excludes from authentication), falling back to GET /stores for
        proxies/versions that do not expose /healthz."""
        async with session.get(f"{self._openfga_url}/healthz") as response:
            if response.status == 404:
                async with session.get(
                    f"{self._openfga_url}/stores", params={"page_size": 1}
                ) as stores_response:
                    return 200 <= stores_response.status < 300
            return 200 <= response.status < 300

    def _set_engine_reachable(self, value: bool) -> None:
        self._engine_reachable = value
        self._transaction_state.set_engine_reachable(value)

    def _get_engine_reachable(self) -> bool:
        return self._engine_reachable

    # ------------------------------------------------------------------
    # backup / restore
    # ------------------------------------------------------------------

    async def full_export(self, writer: AsyncTextIOWrapper) -> None:
        """Exports the combined model and flat tuples to a backup file."""
        async with self._model_lock:
            model = (
                strip_extend(merge_models(list(self._modules.values())))
                if self._modules
                else None
            )
        if self._policy_data_cache is not None:
            tuples = list(self._policy_data_cache)
        else:
            tuples = await self._read_all_tuples()
        await writer.write(json.dumps({"model": model, "tuples": tuples}, default=str))

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        """Restores the store from a backup file (model + tuples)."""
        import_data = json.loads(await reader.read())
        model = import_data.get("model")
        if model:
            await self.set_policy("backup/openfga.json", json.dumps(model))
        await self.set_policy_data(import_data.get("tuples", []))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _chunks(items: List[Dict], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _flatten_tuples(raw_tuples: List[Dict]) -> List[Dict]:
    """Reshapes /read response tuples ({"key": {...}, "timestamp": ...}) into
    the flat {"user", "relation", "object"} shape /write expects."""
    flattened = []
    for raw in raw_tuples:
        key = raw.get("key", raw)
        flattened.append(
            {
                "user": key["user"],
                "relation": key["relation"],
                "object": key["object"],
                **(
                    {"condition": key["condition"]}
                    if key.get("condition") is not None
                    else {}
                ),
            }
        )
    return flattened


def _upsert_tuples(existing: List[Dict], new_tuples: List[Dict]) -> List[Dict]:
    """Adds/updates tuples in a cached list (keyed by user/relation/object)."""
    index = {
        (t["user"], t["relation"], t["object"]): position
        for position, t in enumerate(existing)
    }
    result = list(existing)
    for tuple_data in new_tuples:
        key = (tuple_data["user"], tuple_data["relation"], tuple_data["object"])
        if key in index:
            result[index[key]] = tuple_data
        else:
            index[key] = len(result)
            result.append(tuple_data)
    return result
