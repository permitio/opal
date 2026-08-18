"""OpenFGA policy-store client.

Design note (bounty issue permitio/opal#661): OpenFGA's data model does not
map onto OPA/Cedar's "named policy files" shape. OPA and Cedar let you push
independent policy modules by id; OpenFGA has exactly one authorization
model per store, and models are immutable/versioned rather than patched in
place. So:

- `set_policies(bundle)` compiles every module in the bundle into a single
  combined authorization model and writes it once, instead of looping a
  per-module `set_policy()` call the way Cedar does. `set_policy`,
  `get_policy`, `delete_policy`, and `get_policy_module_ids` are therefore
  left unimplemented (inheriting `NotImplementedError` from
  `BasePolicyStoreClient`) — same as Cedar leaves several methods
  unimplemented, because there is no per-file operation to perform.
- `set_policy_data` / `delete_policy_data` / `get_data` map onto OpenFGA's
  relationship tuples (its analogue of "data"/facts) via the real
  `/write` and `/read` endpoints.

Endpoint paths and request/response shapes below were verified against
OpenFGA's own OpenAPI spec (github.com/openfga/api,
docs/openapiv2/apidocs.swagger.json), not guessed.

Known gaps, left for a deliberate follow-up rather than silently guessed at:
- No REST health-check endpoint exists in OpenFGA's spec, so the liveness
  probe hits `GET /stores` instead — a real, cheap, store-agnostic endpoint.
- OAuth is not supported here, matching Cedar's stance — OpenFGA does
  support OIDC in some deployments, but wiring that up is separate work.
- `authorization_model_id` pinning (OpenFGA's own recommended practice for
  Check/Write calls) isn't implemented; writes target the latest model
  implicitly by omitting `authorization_model_id` from `/write`.
- Relationship conditions (`TupleKey.condition`) aren't supported; tuples
  are plain (user, relation, object) triples.
- `store_id` is read from the `POLICY_STORE_OPENFGA_STORE_ID` environment
  variable directly at construction time as a pragmatic MVP choice — a real
  `confi`-declared config option in opal_client/config.py (mirroring how
  POLICY_STORE_URL etc. are declared) is the correct long-term home for it.
"""
import asyncio
import json
import os
from typing import Dict, List, Optional

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
)
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.store import StoreTransaction, TransactionType
from tenacity import retry


class OpenFGAClient(LivenessProbeMixin, BasePolicyStoreClient):
    def __init__(
        self,
        openfga_server_url: str = None,
        openfga_auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        store_id: Optional[str] = None,
    ):
        base_url = openfga_server_url or opal_client_config.POLICY_STORE_URL
        self._openfga_url = base_url.rstrip("/")
        self._store_id = store_id or os.environ.get("POLICY_STORE_OPENFGA_STORE_ID")
        self._policy_version: Optional[str] = None
        self._lock = asyncio.Lock()
        self._token = openfga_auth_token
        self._auth_type: PolicyStoreAuth = auth_type

        self._had_successful_data_transaction = False
        self._had_successful_policy_transaction = False
        self._most_recent_data_transaction: Optional[StoreTransaction] = None
        self._most_recent_policy_transaction: Optional[StoreTransaction] = None

        # Defaults to True so /healthy preserves historical behavior;
        # start_liveness_probe() runs an initial sample synchronously and
        # overwrites this before the probe loop begins (mirrors Cedar/OPA).
        self._engine_reachable: bool = True
        self._init_liveness_probe()

        if auth_type == PolicyStoreAuth.TOKEN:
            if self._token is None:
                logger.error("POLICY_STORE_AUTH_TOKEN can not be empty")
                raise TypeError("required variables for token auth are not set")
        elif auth_type == PolicyStoreAuth.OAUTH:
            raise ValueError("OpenFGA client does not support OAuth yet.")

        if not self._store_id:
            raise TypeError(
                "OpenFGA policy store requires a store id. Set "
                "POLICY_STORE_OPENFGA_STORE_ID, or pass store_id= explicitly."
            )

        logger.info(f"Authentication mode for policy store: {auth_type}")

    def _store_url(self, suffix: str = "") -> str:
        return f"{self._openfga_url}/stores/{self._store_id}{suffix}"

    async def _get_auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._auth_type == PolicyStoreAuth.TOKEN and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        """Compiles every module in the bundle into ONE authorization model
        and writes it once. Each module's `.rego` text field is expected to
        already contain JSON-encoded OpenFGA type_definitions — the DSL ->
        JSON transpile itself is out of scope here; modules are expected to
        be produced in that JSON form upstream of OPAL (e.g. via the FGA
        CLI's `model transform` command) before being committed to the
        policy repo."""
        type_definitions: List[dict] = []
        for module in bundle.policy_modules:
            try:
                parsed = json.loads(module.rego)
            except json.JSONDecodeError as e:
                logger.error(
                    "OpenFGA policy module {path} is not valid JSON type_definitions: {err}",
                    path=module.path,
                    err=repr(e),
                )
                raise
            if isinstance(parsed, list):
                type_definitions.extend(parsed)
            elif isinstance(parsed, dict) and "type_definitions" in parsed:
                type_definitions.extend(parsed["type_definitions"])
            else:
                type_definitions.append(parsed)

        if not type_definitions:
            logger.info("No OpenFGA type_definitions in bundle; skipping model write.")
            return

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers()
                async with session.post(
                    self._store_url("/authorization-models"),
                    json={"type_definitions": type_definitions, "schema_version": "1.1"},
                    headers=headers,
                ) as response:
                    if response.status != 201:
                        body = await response.text()
                        raise ValueError(
                            "OpenFGA Client: unexpected status writing authorization "
                            f"model: {response.status}, body: {body}"
                        )
                    result = await response.json()
                    self._policy_version = result.get("authorization_model_id")
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        """`policy_data` must be a list of {"user", "relation", "object"}
        dicts — OpenFGA relationship tuples, OPAL's closest analogue to
        arbitrary "data". There is no sub-path write in OpenFGA's tuple
        model, so (matching Cedar's identical constraint, for the same
        reason) a non-empty path is rejected rather than silently ignored."""
        if path != "":
            raise ValueError("OpenFGA can only write the entire tuple set at once.")
        if not isinstance(policy_data, list):
            logger.warning(
                "OPAL client was instructed to put something that is not a list of "
                "tuples on OpenFGA. This will probably not work."
            )
            return None

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers()
                async with session.post(
                    self._store_url("/write"),
                    json={"writes": {"tuple_keys": policy_data, "on_duplicate": "ignore"}},
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise ValueError(
                            "OpenFGA Client: unexpected status writing tuples: "
                            f"{response.status}, body: {body}"
                        )
                    return await response.json()
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        """OpenFGA has no single "clear everything" call (unlike Cedar's
        `DELETE /data`) — deleting a tuple requires naming it explicitly. So
        this reads every current tuple (paginating through /read) and issues
        one /write call with all of them as `deletes`."""
        if path != "":
            raise ValueError("OpenFGA can only clear the entire tuple set at once.")

        tuples = await self._read_all_tuples()
        if not tuples:
            return None

        delete_keys = [
            {
                "user": t["key"]["user"],
                "relation": t["key"]["relation"],
                "object": t["key"]["object"],
            }
            for t in tuples
        ]

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers()
                async with session.post(
                    self._store_url("/write"),
                    json={"deletes": {"tuple_keys": delete_keys, "on_missing": "ignore"}},
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise ValueError(
                            "OpenFGA Client: unexpected status deleting tuples: "
                            f"{response.status}, body: {body}"
                        )
                    return await response.json()
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    async def _read_all_tuples(self) -> List[dict]:
        """Pages through POST /read (no filter = all tuples) until the
        response's continuation_token comes back empty."""
        tuples: List[dict] = []
        continuation_token = ""
        headers = await self._get_auth_headers()
        async with aiohttp.ClientSession(trust_env=True) as session:
            while True:
                body: Dict[str, object] = {"page_size": 100}
                if continuation_token:
                    body["continuation_token"] = continuation_token
                async with session.post(
                    self._store_url("/read"), json=body, headers=headers
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise ValueError(
                            "OpenFGA Client: unexpected status reading tuples: "
                            f"{response.status}, body: {text}"
                        )
                    result = await response.json()
                    tuples.extend(result.get("tuples", []))
                    continuation_token = result.get("continuation_token", "")
                    if not continuation_token:
                        break
        return tuples

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str) -> Dict:
        """Returns all relationship tuples as {"tuples": [...]} — OpenFGA's
        closest match to OPA/Cedar's "get everything at this data path"."""
        if path != "":
            raise ValueError("OpenFGA can only read the entire tuple set at once.")
        tuples = await self._read_all_tuples()
        return {"tuples": tuples}

    async def log_transaction(self, transaction: StoreTransaction):
        if transaction.transaction_type == TransactionType.policy:
            self._most_recent_policy_transaction = transaction
            if transaction.success:
                self._had_successful_policy_transaction = True
        elif transaction.transaction_type == TransactionType.data:
            self._most_recent_data_transaction = transaction
            if transaction.success:
                self._had_successful_data_transaction = True

    async def is_ready(self) -> bool:
        return (
            self._had_successful_policy_transaction
            and self._had_successful_data_transaction
        )

    async def is_healthy(self) -> bool:
        transactions_healthy: bool = (
            self._most_recent_policy_transaction is not None
            and self._most_recent_policy_transaction.success
        ) and (
            self._most_recent_data_transaction is not None
            and self._most_recent_data_transaction.success
        )
        return transactions_healthy and self._engine_reachable

    @property
    def _probe_log_label(self) -> str:
        return "OpenFGA"

    async def _probe_engine_reachable(self, session: aiohttp.ClientSession) -> bool:
        """OpenFGA's OpenAPI spec has no dedicated health-check REST path,
        so this hits `GET /stores` — a real, cheap, store-agnostic endpoint
        that only requires the server to be up and answering."""
        async with session.get(f"{self._openfga_url}/stores?page_size=1") as response:
            return 200 <= response.status < 300

    def _set_engine_reachable(self, value: bool) -> None:
        self._engine_reachable = value

    def _get_engine_reachable(self) -> bool:
        return self._engine_reachable

    async def full_export(self, writer: AsyncTextIOWrapper) -> None:
        tuples = await self._read_all_tuples()
        headers = await self._get_auth_headers()
        model = None
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(
                self._store_url("/authorization-models?page_size=1"), headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    models = result.get("authorization_models", [])
                    model = models[0] if models else None
        await writer.write(json.dumps({"model": model, "tuples": tuples}, default=str))

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        import_data = json.loads(await reader.read())
        model = import_data.get("model")
        if model:
            async with aiohttp.ClientSession(trust_env=True) as session:
                headers = await self._get_auth_headers()
                await session.post(
                    self._store_url("/authorization-models"),
                    json={
                        "type_definitions": model.get("type_definitions", []),
                        "schema_version": model.get("schema_version", "1.1"),
                    },
                    headers=headers,
                )
        await self.set_policy_data(import_data.get("tuples", []))
