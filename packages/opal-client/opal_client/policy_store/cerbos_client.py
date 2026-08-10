import asyncio
import json
from typing import Dict, List, Optional

import aiohttp
import yaml
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

# Top-level keys that identify a parsed file as an actual Cerbos policy
# (as opposed to some other .json/.yaml file that happens to share the
# extension bundle-makers use to select "policy" files - see _parse_policy_file).
_CERBOS_POLICY_KIND_KEYS = (
    "resourcePolicy",
    "principalPolicy",
    "derivedRoles",
    "exportVariables",
    "exportConstants",
)

# Cerbos's AddOrUpdatePolicy admin API request caps at 100 policies per call.
_MAX_POLICIES_PER_REQUEST = 100


class CerbosClient(LivenessProbeMixin, BasePolicyStoreClient):
    """Policy store client for Cerbos.

    Cerbos decisions are computed from principal/resource attributes passed
    in each request rather than from server-stored data documents (unlike
    OPA), so this client has no real equivalent of set_policy_data - see the
    no-op implementations below.
    """

    def __init__(
        self,
        cerbos_server_url=None,
        cerbos_auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        admin_username: Optional[str] = None,
        admin_password: Optional[str] = None,
    ):
        base_url = cerbos_server_url or opal_client_config.POLICY_STORE_URL
        self._cerbos_url = base_url.rstrip("/")
        self._policy_version: Optional[str] = None
        self._lock = asyncio.Lock()
        self._token = cerbos_auth_token
        self._auth_type: PolicyStoreAuth = auth_type
        self._admin_auth = aiohttp.BasicAuth(
            admin_username or opal_client_config.CERBOS_ADMIN_USERNAME,
            admin_password or opal_client_config.CERBOS_ADMIN_PASSWORD,
        )

        self._had_successful_data_transaction = False
        self._had_successful_policy_transaction = False
        self._most_recent_data_transaction: Optional[StoreTransaction] = None
        self._most_recent_policy_transaction: Optional[StoreTransaction] = None

        # `_engine_reachable` defaults to True so /healthy preserves historical
        # behavior; `start_liveness_probe()` runs an initial sample synchronously
        # and overwrites this before the probe loop begins.
        self._engine_reachable: bool = True
        self._init_liveness_probe()

        if auth_type == PolicyStoreAuth.OAUTH:
            raise ValueError("Cerbos doesn't support OAuth.")
        if auth_type == PolicyStoreAuth.TOKEN and self._token is None:
            logger.error("POLICY_STORE_AUTH_TOKEN can not be empty")
            raise TypeError("required variables for token auth are not set")

        logger.info(f"Authentication mode for policy store: {auth_type}")

    async def _get_auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._auth_type == PolicyStoreAuth.TOKEN and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @staticmethod
    def _parse_policy_file(path: str, content: str) -> Optional[dict]:
        """Parse a bundle file's content as a Cerbos policy.

        Returns None (and logs) if the file doesn't actually look like a
        Cerbos policy - e.g. a data file that happens to share the .json/
        .yaml extension bundle-makers use to select "policy" files, or one
        of the *_test.yaml test-suite files Cerbos example repos ship
        alongside real policies.
        """
        try:
            if path.endswith((".yaml", ".yml")):
                parsed = yaml.safe_load(content)
            elif path.endswith(".json"):
                parsed = json.loads(content)
            else:
                return None
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            logger.warning(f"Skipping unparsable Cerbos policy file {path}: {e}")
            return None

        if not isinstance(parsed, dict) or "apiVersion" not in parsed:
            logger.debug(f"Skipping {path}: does not look like a Cerbos policy")
            return None
        if not any(key in parsed for key in _CERBOS_POLICY_KIND_KEYS):
            logger.debug(f"Skipping {path}: no recognized Cerbos policy kind")
            return None
        return parsed

    async def _push_policies(self, policies: List[dict]) -> None:
        # Cerbos's AddOrUpdatePolicy request caps at 100 policies per call.
        for i in range(0, len(policies), _MAX_POLICIES_PER_REQUEST):
            await self._push_policies_batch(policies[i : i + _MAX_POLICIES_PER_REQUEST])

    async def _push_policies_batch(self, policies: List[dict]) -> None:
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                async with session.put(
                    f"{self._cerbos_url}/admin/policy",
                    json={"policies": policies},
                    auth=self._admin_auth,
                ) as response:
                    if response.status >= 400:
                        body = await response.text()
                        raise Exception(
                            f"Failed to push policies to Cerbos: HTTP {response.status} - {body}"
                        )
            except aiohttp.ClientError as e:
                logger.warning("Cerbos connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy(
        self,
        policy_id: str,
        policy_code: str,
        transaction_id: Optional[str] = None,
    ):
        """Push a single policy (JSON-encoded Cerbos policy document) to
        Cerbos's admin API."""
        await self._push_policies([json.loads(policy_code)])

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                async with session.get(
                    f"{self._cerbos_url}/admin/policy",
                    params={"id": policy_id},
                    auth=self._admin_auth,
                ) as response:
                    result = await response.json()
                    policies = result.get("policies", [])
                    return json.dumps(policies[0]) if policies else None
            except aiohttp.ClientError as e:
                logger.warning("Cerbos connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy_module_ids(self) -> List[str]:
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                async with session.get(
                    f"{self._cerbos_url}/admin/policies", auth=self._admin_auth
                ) as response:
                    result = await response.json()
                    return result.get("policyIds", [])
            except aiohttp.ClientError as e:
                logger.warning("Cerbos connection error: {err}", err=repr(e))
                raise

    async def get_policies(self) -> Optional[Dict[str, str]]:
        ids = await self.get_policy_module_ids() or []
        policies: Dict[str, str] = {}
        for policy_id in ids:
            content = await self.get_policy(policy_id)
            if content is not None:
                policies[policy_id] = content
        return policies

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                async with session.post(
                    f"{self._cerbos_url}/admin/policy/delete",
                    params={"id": policy_id},
                    auth=self._admin_auth,
                ) as response:
                    if response.status >= 400:
                        body = await response.text()
                        raise Exception(
                            f"Failed to delete Cerbos policy {policy_id}: HTTP {response.status} - {body}"
                        )
            except aiohttp.ClientError as e:
                logger.warning("Cerbos connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        policies = []
        for module in bundle.policy_modules:
            parsed = self._parse_policy_file(module.path, module.rego)
            if parsed is not None:
                policies.append(parsed)

        if policies:
            await self._push_policies(policies)

        # Deliberately no diff-and-delete step here (unlike the OPA/Cedar
        # clients): Cerbos's policy id format depends on the backing store
        # (a filename for disk/git/blob stores, a kind.name.version triple
        # for SQL stores) and isn't reliably derivable here, so a wrong
        # guess could delete the wrong policy. Removing a file from the
        # repo currently leaves the old policy in Cerbos until deleted
        # directly (e.g. via cerbosctl).
        self._policy_version = bundle.hash

    # Cerbos has no server-stored data-document concept: decisions are
    # computed from attributes passed in each check request, not from data
    # OPAL pushes ahead of time. These are no-ops so /ready's data component
    # (which requires at least one successful data transaction, same as
    # every other backend) is satisfied without pretending to sync anything.
    @affects_transaction
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        logger.debug(
            "Ignoring data update for Cerbos - Cerbos has no data-document store, "
            "decisions use attributes passed in each check request"
        )

    @affects_transaction
    async def patch_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        await self.set_policy_data(
            policy_data, path=path, transaction_id=transaction_id
        )

    @affects_transaction
    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        pass

    async def get_data(self, path: str) -> Dict:
        return {}

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
        return "Cerbos"

    async def _probe_engine_reachable(self, session: aiohttp.ClientSession) -> bool:
        health_url = f"{self._cerbos_url}/_cerbos/health"
        async with session.get(health_url) as response:
            return response.status == 200

    def _set_engine_reachable(self, value: bool) -> None:
        self._engine_reachable = value

    def _get_engine_reachable(self) -> bool:
        return self._engine_reachable

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version

    async def full_export(self, writer: AsyncTextIOWrapper) -> None:
        policies = await self.get_policies()
        await writer.write(json.dumps({"policies": policies, "data": {}}, default=str))

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        import_data = json.loads(await reader.read())
        for policy_id, raw in import_data["policies"].items():
            await self.set_policy(policy_id=policy_id, policy_code=raw)
