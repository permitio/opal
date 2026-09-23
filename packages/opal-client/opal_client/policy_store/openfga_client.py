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
import copy
import hashlib
import json
import os
import tempfile
from typing import Any, Dict, List, Optional

import aiofiles
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

    The state honors disabled updaters (unlike the Cedar client): a
    disabled updater can never fail, so it must not render the store
    not-ready.
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
        module_state_path: Optional[str] = None,
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
        self._module_state_path = module_state_path or _openfga_module_state_path(
            self._openfga_url,
            self._store_id or f"name:{self._store_name}",
            opal_client_config.STORE_BACKUP_PATH,
        )
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

        self._modules: Dict[str, Dict] = {}
        self._base_model: Optional[Dict] = None
        self._data_modules: Dict[str, List[Dict]] = {}
        self._owned_tuples: Dict[Any, Dict] = {}
        self._state_loaded = False
        self._state_from_file = False
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
        """Returns the configured store id, creating/looking up a store by name
        when none was configured (OpenFGA ids are server generated)."""
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

    async def _read_latest_authorization_model(self) -> Optional[Dict]:
        await self._ensure_store_id()
        headers = self._get_auth_headers()
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(
                self._store_url("/authorization-models"),
                params={"page_size": 1},
                headers=headers,
            ) as response:
                if response.status != 200:
                    raise ValueError(
                        f"failed listing OpenFGA authorization models: HTTP {response.status}"
                    )
                result = await response.json()
            model_ids = result.get("authorization_model_ids") or []
            if not model_ids:
                return None
            async with session.get(
                f"{self._store_url('/authorization-models')}/{model_ids[0]}",
                headers=headers,
            ) as response:
                if response.status != 200:
                    raise ValueError(
                        f"failed reading OpenFGA authorization model: HTTP {response.status}"
                    )
                return normalize_model(await response.json())

    async def _load_state(self, reconstruct_model: bool) -> None:
        if self._state_loaded:
            return
        await self._ensure_store_id()
        if os.path.exists(self._module_state_path):
            try:
                async with aiofiles.open(self._module_state_path, "r") as state_file:
                    payload = json.loads(await state_file.read())
                if payload.get("version") != 1:
                    raise ValueError("unsupported OpenFGA state version")
                if payload.get("store_id") != self._store_id:
                    raise ValueError("OpenFGA state belongs to a different store")
                modules = {
                    str(path): normalize_model(fragment)
                    for path, fragment in payload.get("modules", {}).items()
                }
                data_modules = {
                    str(path): convert_to_tuples(tuples)
                    for path, tuples in payload.get("data_modules", {}).items()
                }
                owned_tuples = convert_to_tuples(payload.get("tuples", []))
                base_model = payload.get("base_model")
                self._modules = modules
                self._data_modules = data_modules
                self._owned_tuples = {
                    _tuple_key(tuple_data): tuple_data for tuple_data in owned_tuples
                }
                self._base_model = (
                    normalize_model(base_model) if base_model is not None else None
                )
                self._state_from_file = True
                self._state_loaded = True
                return
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
                json.JSONDecodeError,
            ) as err:
                logger.warning(
                    "Ignoring invalid OpenFGA module state {path}: {err}",
                    path=self._module_state_path,
                    err=repr(err),
                )
        if reconstruct_model:
            try:
                self._base_model = await self._read_latest_authorization_model()
            except (
                aiohttp.ClientError,
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
            ) as err:
                logger.warning(
                    "Could not reconstruct existing OpenFGA authorization model: {err}",
                    err=repr(err),
                )
        self._state_loaded = True

    async def _persist_state(self) -> None:
        state = {
            "version": 1,
            "store_id": self._store_id,
            "modules": self._modules,
            "base_model": self._base_model,
            "data_modules": self._data_modules,
            "tuples": list(self._owned_tuples.values()),
        }
        directory = os.path.dirname(self._module_state_path) or "."
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            dir=directory, prefix=".openfga-state-", suffix=".tmp"
        )
        os.close(descriptor)
        try:
            async with aiofiles.open(temporary_path, "w") as state_file:
                await state_file.write(json.dumps(state, sort_keys=True))
            os.chmod(temporary_path, 0o600)
            await aiofiles.os.replace(temporary_path, self._module_state_path)
            self._state_from_file = True
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

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

    async def _write_combined_model(
        self, modules: Dict[str, Dict], base_model: Optional[Dict]
    ) -> Optional[str]:
        model = _combined_authorization_model(modules, base_model)
        if model is None:
            return None
        body: Dict[str, Any] = {
            "schema_version": model["schema_version"],
            "type_definitions": model["type_definitions"],
        }
        if model.get("conditions"):
            body["conditions"] = model["conditions"]

        await self._ensure_store_id()
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
                    n=len(modules),
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
            await self._load_state(reconstruct_model=True)
            modules = dict(self._modules)
            modules[policy_id] = self._parse_policy_code(policy_id, policy_code)
            model_id = await self._write_combined_model(modules, self._base_model)
            self._modules = modules
            if model_id is not None:
                self._policy_version = model_id
            await self._persist_state()

    @affects_transaction
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        async with self._model_lock:
            full_bundle = bundle.old_hash is None
            await self._load_state(reconstruct_model=not full_bundle)
            modules = {} if full_bundle else dict(self._modules)
            data_modules = (
                {}
                if full_bundle
                else {path: list(tuples) for path, tuples in self._data_modules.items()}
            )
            deleted_modules = []
            deleted_data_modules = []
            if bundle.old_hash is not None and bundle.deleted_files is not None:
                deleted_modules = [
                    str(module) for module in bundle.deleted_files.policy_modules
                ]
                deleted_data_modules = [
                    str(module) for module in bundle.deleted_files.data_modules
                ]
            for module_id in deleted_modules:
                modules.pop(module_id, None)
            for module_id in deleted_data_modules:
                data_modules.pop(module_id, None)

            for policy in bundle.policy_modules:
                modules[policy.path] = self._parse_policy_code(policy.path, policy.rego)

            for module in bundle.data_modules:
                try:
                    module_data = json.loads(module.data)
                    data_modules[module.path] = convert_to_tuples(module_data)
                except (json.JSONDecodeError, TupleConversionError) as err:
                    logger.warning(
                        "bundle contains invalid data module {module_path}: {err}",
                        module_path=module.path,
                        err=repr(err),
                    )

            stale_keys = set()
            for path, old_tuples in self._data_modules.items():
                if data_modules.get(path) != old_tuples:
                    stale_keys.update(
                        _tuple_key(tuple_data) for tuple_data in old_tuples
                    )
            candidate_owned = {
                key: tuple_data
                for key, tuple_data in self._owned_tuples.items()
                if key not in stale_keys
            }
            for tuples in data_modules.values():
                for tuple_data in tuples:
                    candidate_owned[_tuple_key(tuple_data)] = tuple_data

            if not modules:
                stale_keys = set(candidate_owned)
                candidate_owned = {}
                data_modules = {}
                tuples_to_write = []
            else:
                tuples_to_write = [
                    tuple_data
                    for tuples in data_modules.values()
                    for tuple_data in tuples
                    if self._owned_tuples.get(_tuple_key(tuple_data)) != tuple_data
                ]

            stale_tuples = [
                self._owned_tuples[key]
                for key in stale_keys
                if key in self._owned_tuples
            ]
            for chunk in _chunks(stale_tuples, self._max_tuples_per_write):
                await self._write_tuples(deletes=chunk)

            base_model = None if full_bundle else self._base_model
            model_id = await self._write_combined_model(modules, base_model)
            if model_id is not None:
                self._policy_version = model_id
            for chunk in _chunks(tuples_to_write, self._max_tuples_per_write):
                await self._write_tuples(writes=chunk)

            self._modules = modules
            self._base_model = base_model
            self._data_modules = data_modules
            self._owned_tuples = candidate_owned
            if model_id is None and not modules:
                self._policy_version = None
            await self._persist_state()

            if deleted_modules:
                logger.warning(
                    "OpenFGA authorization models are immutable - deleted "
                    "policy modules {modules} were removed from the combined "
                    "model, which was re-written as a new version",
                    modules=deleted_modules,
                )
        logger.debug("OpenFGA set_policies done, bundle hash {hash}", hash=bundle.hash)

    @fail_silently()
    @retry(**RETRY_CONFIG, reraise=True)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        async with self._model_lock:
            await self._load_state(reconstruct_model=True)
            module = self._modules.get(policy_id)
        if module is None:
            return None
        return json.dumps(module)

    @fail_silently()
    @retry(**RETRY_CONFIG, reraise=True)
    async def get_policies(self) -> Optional[Dict[str, str]]:
        async with self._model_lock:
            await self._load_state(reconstruct_model=True)
            return {path: json.dumps(module) for path, module in self._modules.items()}

    async def get_policy_module_ids(self) -> List[str]:
        async with self._model_lock:
            await self._load_state(reconstruct_model=True)
            return list(self._modules.keys())

    @affects_transaction
    @retry(**RETRY_CONFIG, reraise=True)
    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring deleting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return
        async with self._model_lock:
            await self._load_state(reconstruct_model=True)
            if policy_id not in self._modules:
                logger.warning(
                    "attempted to delete unknown OpenFGA policy module {id}",
                    id=policy_id,
                )
                return
            modules = dict(self._modules)
            del modules[policy_id]
            if modules:
                model_id = await self._write_combined_model(modules, self._base_model)
            else:
                model_id = None
                owned = list(self._owned_tuples.values())
                for chunk in _chunks(owned, self._max_tuples_per_write):
                    await self._write_tuples(deletes=chunk)
                self._data_modules = {}
                self._owned_tuples = {}
                self._base_model = None
            self._modules = modules
            if model_id is not None:
                self._policy_version = model_id
            elif not modules:
                self._policy_version = None
            await self._persist_state()

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

        async with self._model_lock:
            await self._load_state(reconstruct_model=False)
            for chunk in _chunks(tuples, self._max_tuples_per_write):
                await self._write_tuples(writes=chunk)
            for tuple_data in tuples:
                self._owned_tuples[_tuple_key(tuple_data)] = tuple_data
            if self._policy_data_cache is not None:
                self._policy_data_cache = _upsert_tuples(
                    self._policy_data_cache, tuples
                )
            await self._persist_state()

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
        async with self._model_lock:
            await self._load_state(reconstruct_model=False)
            object_filter = path if ":" in path else ""
            existing = (
                await self._read_all_tuples(object_filter=object_filter) if path else []
            )
            existing = filter_tuples_by_object_prefix(existing, path)
            owned_matching = [
                tuple_data
                for tuple_data in self._owned_tuples.values()
                if filter_tuples_by_object_prefix([tuple_data], path)
            ]
            delete_by_key = {
                _tuple_key(tuple_data): {
                    "user": tuple_data["user"],
                    "relation": tuple_data["relation"],
                    "object": tuple_data["object"],
                }
                for tuple_data in [*existing, *owned_matching]
            }
            if not delete_by_key:
                logger.info(
                    "No tuples matched path {path!r}; nothing to delete", path=path
                )
                return
            delete_keys = list(delete_by_key.values())
            for chunk in _chunks(delete_keys, self._max_tuples_per_write):
                await self._write_tuples(deletes=chunk)
            for key in delete_by_key:
                self._owned_tuples.pop(key, None)
            if self._policy_data_cache is not None:
                self._policy_data_cache = [
                    tuple_data
                    for tuple_data in self._policy_data_cache
                    if _tuple_key(tuple_data) not in delete_by_key
                ]
            await self._persist_state()

    @fail_silently(fallback={"tuples": []})
    @retry(**RETRY_CONFIG, reraise=True)
    async def get_data(self, path: str) -> Dict:
        """Returns relationship tuples as {"tuples": [...]} (flat write-shaped
        tuples).

        When `path` is given, only tuples whose object matches the
        path (exact match or prefix) are returned.
        """
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

        await self._ensure_store_id()
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
        await self._ensure_store_id()
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
        async with self._model_lock:
            await self._load_state(reconstruct_model=True)
            model = _combined_authorization_model(self._modules, self._base_model)
            modules = copy.deepcopy(self._modules)
            base_model = copy.deepcopy(self._base_model)
            data_modules = copy.deepcopy(self._data_modules)
            if self._state_from_file:
                tuples = list(self._owned_tuples.values())
            elif self._policy_data_cache is not None:
                tuples = list(self._policy_data_cache)
            else:
                tuples = await self._read_all_tuples()
        await writer.write(
            json.dumps(
                {
                    "model": model,
                    "modules": modules,
                    "base_model": base_model,
                    "data_modules": data_modules,
                    "tuples": tuples,
                },
                default=str,
            )
        )

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        import_data = json.loads(await reader.read())
        raw_modules = import_data.get("modules")
        if raw_modules is None:
            model = import_data.get("model")
            modules = (
                {"backup/openfga.json": normalize_model(model)}
                if model is not None
                else {}
            )
        else:
            modules = {
                str(path): normalize_model(fragment)
                for path, fragment in raw_modules.items()
            }
        base_model = import_data.get("base_model")
        base_model = normalize_model(base_model) if base_model is not None else None
        data_modules = {
            str(path): convert_to_tuples(tuples)
            for path, tuples in import_data.get("data_modules", {}).items()
        }
        imported_tuples = convert_to_tuples(import_data.get("tuples", []))

        async with self._model_lock:
            await self._load_state(reconstruct_model=False)
            imported_by_key = {
                _tuple_key(tuple_data): tuple_data for tuple_data in imported_tuples
            }
            stale = [
                tuple_data
                for key, tuple_data in self._owned_tuples.items()
                if key not in imported_by_key
            ]
            for chunk in _chunks(stale, self._max_tuples_per_write):
                await self._write_tuples(deletes=chunk)
            model_id = await self._write_combined_model(modules, base_model)
            if model_id is not None:
                self._policy_version = model_id
            for chunk in _chunks(imported_tuples, self._max_tuples_per_write):
                await self._write_tuples(writes=chunk)
            self._modules = modules
            self._base_model = base_model
            self._data_modules = data_modules
            self._owned_tuples = imported_by_key
            if model_id is None and not modules:
                self._policy_version = None
            if self._policy_data_cache is not None:
                self._policy_data_cache = list(imported_tuples)
            await self._persist_state()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _openfga_module_state_path(
    base_url: str, store_reference: str, backup_path: str
) -> str:
    backup_path = backup_path or "opa.json"
    root, extension = os.path.splitext(backup_path)
    digest = hashlib.sha256(
        f"{base_url}\0{store_reference}".encode("utf-8")
    ).hexdigest()[:20]
    return f"{root}.openfga-{digest}{extension or '.json'}"


def _tuple_key(tuple_data: Dict) -> Any:
    return tuple_data["user"], tuple_data["relation"], tuple_data["object"]


def _combined_authorization_model(
    modules: Dict[str, Dict], base_model: Optional[Dict]
) -> Optional[Dict]:
    if not modules:
        return (
            strip_extend(normalize_model(base_model))
            if base_model is not None
            else None
        )
    if base_model is None:
        return strip_extend(merge_models(list(modules.values())))

    incoming = strip_extend(merge_models(list(modules.values())))
    merged = copy.deepcopy(base_model)
    incoming_types = {
        type_definition.get("type")
        for type_definition in incoming.get("type_definitions", [])
    }
    merged["type_definitions"] = [
        type_definition
        for type_definition in merged.get("type_definitions", [])
        if type_definition.get("type") not in incoming_types
    ] + list(incoming.get("type_definitions", []))
    if incoming.get("conditions"):
        conditions = dict(merged.get("conditions", {}))
        conditions.update(incoming["conditions"])
        merged["conditions"] = conditions
    merged["schema_version"] = incoming.get(
        "schema_version", merged.get("schema_version", "1.1")
    )
    return strip_extend(normalize_model(merged))


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
