import asyncio
import json
from typing import Dict, List, Optional, Set, Union
from urllib.parse import quote_plus

import aiohttp
from aiofiles.threadpool.text import AsyncTextIOWrapper
from fastapi import status
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
    proxy_response_unless_invalid,
    should_ignore_path,
)
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.store import StoreTransaction, TransactionType
from tenacity import retry


class OpenFGAClient(LivenessProbeMixin, BasePolicyStoreClient):
    """
    OpenFGA policy store client.

    Communicates with OpenFGA via its REST API (https://openfga.dev/api).
    OpenFGA is a fine-grained authorization system (ReBAC) developed by Okta.
    """

    def __init__(
        self,
        openfga_server_url=None,
        openfga_auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        store_id: Optional[str] = None,
    ):
        base_url = openfga_server_url or opal_client_config.POLICY_STORE_URL
        self._base_url = base_url.rstrip("/")
        self._api_url = f"{self._base_url}/api/v1"
        self._policy_version: Optional[str] = None
        self._lock = asyncio.Lock()
        self._token = openfga_auth_token
        self._auth_type: PolicyStoreAuth = auth_type
        self._store_id: Optional[str] = store_id

        self._had_successful_data_transaction = False
        self._had_successful_policy_transaction = False
        self._most_recent_data_transaction: Optional[StoreTransaction] = None
        self._most_recent_policy_transaction: Optional[StoreTransaction] = None

        self._engine_reachable: bool = True
        self._init_liveness_probe()

        if auth_type == PolicyStoreAuth.TOKEN:
            if self._token is None:
                logger.error("POLICY_STORE_AUTH_TOKEN can not be empty")
                raise TypeError("required variables for token auth are not set")
        elif auth_type == PolicyStoreAuth.OAUTH:
            raise ValueError("OpenFGA doesn't support OAuth via OPAL config; use TOKEN or NONE.")

        logger.info(f"Authentication mode for policy store: {auth_type}")

    async def _get_auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._auth_type == PolicyStoreAuth.TOKEN and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _store_path(self, path: str = "") -> str:
        """Build a path scoped to the configured store."""
        if self._store_id:
            return f"{self._api_url}/stores/{quote_plus(self._store_id)}/{path.lstrip('/')}"
        return f"{self._api_url}/{path.lstrip('/')}"

    # ------------------------------------------------------------------
    # Policy (Authorization Model) operations
    # In OpenFGA, "policies" map to Authorization Models (Type Definitions)
    # ------------------------------------------------------------------

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy(
        self,
        policy_id: str,
        policy_code: str,
        transaction_id: Optional[str] = None,
    ):
        """
        Write an authorization model (type definition) to OpenFGA.

        ``policy_id`` is used as a logical identifier (ignored in the API call,
        since OpenFGA assigns model IDs automatically). ``policy_code`` must be
        a valid OpenFGA authorization model JSON string.
        """
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring setting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return

        try:
            model = json.loads(policy_code)
        except json.JSONDecodeError:
            logger.error(f"OpenFGA: policy_code is not valid JSON for policy_id={policy_id}")
            raise ValueError("OpenFGA authorization model must be valid JSON")

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers()
                async with session.post(
                    self._store_path("authorization-models"),
                    json=model,
                    headers=headers,
                ) as response:
                    return await proxy_response_unless_invalid(
                        response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_201_CREATED,
                            status.HTTP_400_BAD_REQUEST,
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        """Read an authorization model by its ID."""
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers()
                async with session.get(
                    self._store_path(f"authorization-models/{quote_plus(policy_id)}"),
                    headers=headers,
                ) as response:
                    result = await response.json()
                    return json.dumps(result.get("authorization_model", result))
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_authorization_models(self) -> Optional[List[Dict]]:
        """List all authorization models (latest versions)."""
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers()
                async with session.get(
                    self._store_path("authorization-models"),
                    headers=headers,
                ) as response:
                    result = await response.json()
                    return result.get("authorization_models", [])
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy(
        self, policy_id: str, transaction_id: Optional[str] = None
    ):
        """
        OpenFGA does not support deleting individual authorization models.
        This is a no-op with a warning, as per OpenFGA's design.
        """
        logger.warning(
            f"OpenFGA does not support deleting authorization models. Skipping {policy_id}."
        )

    # ------------------------------------------------------------------
    # Data (Relationship Tuples) operations
    # In OpenFGA, "data" maps to relationship tuples (who has what relation to what)
    # ------------------------------------------------------------------

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        """
        Write relationship tuples to OpenFGA.

        ``policy_data`` must be a dict or list of tuples with keys:
        - user: str
        - relation: str
        - object: str
        - condition (optional): dict
        """
        if isinstance(policy_data, dict):
            tuples = policy_data.get("tuples", [])
        elif isinstance(policy_data, list):
            tuples = policy_data
        else:
            raise ValueError("OpenFGA policy_data must be a dict with 'tuples' or a list of tuples")

        if not tuples:
            logger.warning("OpenFGA set_policy_data called with no tuples")
            return

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers()
                async with session.post(
                    self._store_path("write"),
                    json={"writes": {"tuple_keys": tuples}},
                    headers=headers,
                ) as response:
                    return await proxy_response_unless_invalid(
                        response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_400_BAD_REQUEST,
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        """
        OpenFGA does not support bulk delete of relationship tuples by path.
        This is a no-op; use set_policy_data with empty tuples or the OpenFGA
        CLI for cleanup.
        """
        logger.warning(
            "OpenFGA does not support bulk delete by path. "
            "Use the OpenFGA CLI or individual tuple deletes."
        )

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str) -> Dict:
        """
        Read relationship tuples from OpenFGA.

        If ``path`` is provided, it's used as the object filter (read tuples
        for a specific object). Otherwise, reads all tuples (limited to
        1000 by default).
        """
        payload: Dict = {}
        if path:
            payload["object"] = path

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers()
                async with session.post(
                    self._store_path("read"),
                    json=payload,
                    headers=headers,
                ) as response:
                    result = await response.json()
                    return result
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data_with_input(self, path: str, input_model) -> Dict:
        """
        Perform a Check or Expand query on OpenFGA.

        ``path`` is the object key.
        ``input_model`` must be a dict with 'user' and 'relation' keys (for Check),
        or just 'relation' (for Expand).
        """
        if hasattr(input_model, "dict"):
            input_data = input_model.dict()
        else:
            input_data = input_model

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers()

                if "relation" in input_data and "user" in input_data:
                    # Check: does user have relation to object?
                    payload = {
                        "tuple_key": {
                            "user": input_data["user"],
                            "relation": input_data["relation"],
                            "object": path,
                        }
                    }
                    async with session.post(
                        self._store_path("check"),
                        json=payload,
                        headers=headers,
                    ) as response:
                        result = await response.json()
                        return result
                elif "relation" in input_data:
                    # Expand: list all users with this relation on this object
                    payload = {
                        "tuple_key": {
                            "relation": input_data["relation"],
                            "object": path,
                        }
                    }
                    async with session.post(
                        self._store_path("expand"),
                        json=payload,
                        headers=headers,
                    ) as response:
                        result = await response.json()
                        return result
                else:
                    raise ValueError(
                        "OpenFGA get_data_with_input requires 'relation' and optionally 'user'"
                    )
            except aiohttp.ClientError as e:
                logger.warning("OpenFGA connection error: {err}", err=repr(e))
                raise

    # ------------------------------------------------------------------
    # Transaction log
    # ------------------------------------------------------------------

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
        """Probe OpenFGA by hitting the /health endpoint."""
        health_url = f"{self._base_url}/healthz"
        async with session.get(health_url) as response:
            return 200 <= response.status < 300

    def _set_engine_reachable(self, value: bool) -> None:
        self._engine_reachable = value

    def _get_engine_reachable(self) -> bool:
        return self._engine_reachable

    # ------------------------------------------------------------------
    # Bundle operations
    # ------------------------------------------------------------------

    @affects_transaction
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        for policy in bundle.policy_modules:
            await self.set_policy(policy.path, policy.rego)
        self._policy_version = bundle.hash

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version

    # ------------------------------------------------------------------
    # Export/Import for backup
    # ------------------------------------------------------------------

    async def full_export(self, writer: AsyncTextIOWrapper) -> None:
        models = await self.get_authorization_models()
        data = await self.get_data("")
        await writer.write(
            json.dumps({"authorization_models": models, "tuples": data}, default=str)
        )

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        import_data = json.loads(await reader.read())

        for model in import_data.get("authorization_models", []):
            await self.set_policy(
                policy_id=model.get("id", "imported"),
                policy_code=json.dumps(model),
            )

        tuples = import_data.get("tuples", {}).get("tuples", [])
        if tuples:
            await self.set_policy_data([t["key"] for t in tuples])
