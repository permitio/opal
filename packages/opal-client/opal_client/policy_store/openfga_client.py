import asyncio
import json
from typing import Dict, List, Optional, Any
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
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.store import StoreTransaction, TransactionType
from tenacity import retry, stop_after_attempt, wait_exponential

RETRY_CONFIG = {
    "stop": stop_after_attempt(5),
    "wait": wait_exponential(multiplier=1, min=4, max=10),
}

class OpenFGATransactionLogState:
    """State tracker for OpenFGA transactions and health checks."""

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

    @property
    def ready(self) -> bool:
        return self._num_successful_policy_transactions > 0 and (
            self._data_updater_disabled or self._num_successful_data_transactions > 0
        )

    @property
    def healthy(self) -> bool:
        policy_updater_is_healthy: bool = (
            self._last_policy_transaction is not None
            and self._last_policy_transaction.success
        )
        data_updater_is_healthy: bool = (
            self._last_data_transaction is not None
            and self._last_data_transaction.success
        )
        is_healthy: bool = (
            self._policy_updater_disabled or policy_updater_is_healthy
        ) and (self._data_updater_disabled or data_updater_is_healthy)

        if is_healthy:
            logger.debug(
                f"OpenFGA client health: {is_healthy} (policy: {policy_updater_is_healthy}, data: {data_updater_is_healthy})"
            )
        else:
            logger.warning(
                f"OpenFGA client health: {is_healthy} (policy: {policy_updater_is_healthy}, data: {data_updater_is_healthy})"
            )

        return is_healthy

    def process_transaction(self, transaction: StoreTransaction):
        """Process and track transaction state."""
        logger.debug(
            "processing store transaction: {transaction}",
            transaction=transaction.dict(),
        )
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

class OpenFGAClient(BasePolicyStoreClient):
    def __init__(
        self,
        openfga_server_url=None,
        openfga_auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        store_id: Optional[str] = None,
        data_updater_enabled: bool = True,
        policy_updater_enabled: bool = True,
    ):
        base_url = openfga_server_url or opal_client_config.POLICY_STORE_URL
        self._openfga_url = base_url.rstrip('/')
        self._store_id = store_id or opal_client_config.OPENFGA_STORE_ID
        self._base_url = f"{self._openfga_url}/stores/{self._store_id}"
        self._policy_version: Optional[str] = None
        self._lock = asyncio.Lock()
        self._token = openfga_auth_token
        self._auth_type: PolicyStoreAuth = auth_type
        self._session: Optional[aiohttp.ClientSession] = None

        # Initialize transaction tracking
        self._transaction_state = OpenFGATransactionLogState(
            data_updater_enabled=data_updater_enabled,
            policy_updater_enabled=policy_updater_enabled,
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session with proper headers."""
        if self._session is None or self._session.closed:
            headers = {"Content-Type": "application/json"}
            if self._auth_type == PolicyStoreAuth.TOKEN and self._token is not None:
                headers["Authorization"] = f"Bearer {self._token}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    @retry(**RETRY_CONFIG)
    async def set_policy(
        self,
        policy_id: str,
        policy_code: str,
        transaction_id: Optional[str] = None,
    ):
        """Write an authorization model to OpenFGA."""
        try:
            logger.debug(f"Attempting to set policy with ID {policy_id}: {policy_code}")
            policy = json.loads(policy_code)

            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/authorization-models",
                json=policy
            ) as response:
                if response.status == 201:
                    data = await response.json()
                    self._policy_version = data["authorization_model_id"]
                    logger.info(f"Successfully set policy with model ID: {self._policy_version}")
                    return data
                else:
                    error_body = await response.text()
                    logger.error(f"Error setting policy: {error_body}")
                    raise Exception(f"Failed to set policy: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error in set_policy: {str(e)}")
            raise

    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        """Get an authorization model by ID."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self._base_url}/authorization-models/{policy_id}"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return json.dumps(data["authorization_model"])
                return None
        except Exception as e:
            logger.error(f"Error in get_policy: {str(e)}")
            return None

    @retry(**RETRY_CONFIG)
    async def get_policies(self) -> Optional[Dict[str, str]]:
        """Get all authorization models."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self._base_url}/authorization-models"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        model["id"]: json.dumps(model)
                        for model in data.get("authorization_models", [])
                    }
                return None
        except Exception as e:
            logger.error(f"Error in get_policies: {str(e)}")
            return None

    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        """OpenFGA does not support deletion of authorization models."""
        logger.warning("Deleting policies is not supported in OpenFGA")
        return None

    @retry(**RETRY_CONFIG)
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        """Set relationship tuples in OpenFGA."""
        try:
            logger.debug(f"Setting policy data: {policy_data}")
            
            # Transform data into tuples if needed
            if isinstance(policy_data, dict) and "tuples" in policy_data:
                tuples = policy_data["tuples"]
            elif isinstance(policy_data, list):
                tuples = policy_data
            else:
                logger.warning(f"Invalid policy data format: {policy_data}")
                return

            writes = {
                "writes": {
                    "tuple_keys": [
                        {
                            "user": tuple["user"],
                            "relation": tuple["relation"],
                            "object": tuple["object"]
                        } for tuple in tuples
                    ]
                }
            }

            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/write",
                json=writes
            ) as response:
                if response.status != 200:
                    error_body = await response.text()
                    raise Exception(f"Failed to set policy data: {error_body}")
                logger.info(f"Successfully wrote {len(tuples)} tuples")

        except Exception as e:
            logger.error(f"Error in set_policy_data: {str(e)}")
            raise

    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str = "") -> Dict:
        """Get relationship tuples, optionally filtered by path."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/read",
                json={"tuple_key": {"object": path} if path else {}}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "tuples": [
                            {
                                "user": tuple["key"]["user"],
                                "relation": tuple["key"]["relation"],
                                "object": tuple["key"]["object"]
                            }
                            for tuple in data.get("tuples", [])
                        ]
                    }
                return {}
        except Exception as e:
            logger.error(f"Error in get_data: {str(e)}")
            return {}

    async def get_data_with_input(self, path: str, input_model: Any) -> Dict:
        """Check authorization with context."""
        try:
            input_data = input_model.dict()
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/check",
                json={
                    "tuple_key": {
                        "user": input_data.get("user"),
                        "relation": input_data.get("relation"),
                        "object": path
                    },
                    "context": input_data.get("context", {})
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "allowed": data.get("allowed", False),
                        "resolution": data.get("resolution")
                    }
                return {"allowed": False}
        except Exception as e:
            logger.error(f"Error in get_data_with_input: {str(e)}")
            return {"allowed": False}

    async def patch_policy_data(
        self,
        policy_data: List[Dict],
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        """OpenFGA doesn't support patches directly - implementing as a write."""
        return await self.set_policy_data(policy_data, path, transaction_id)

    async def check_permission(self, user: str, relation: str, object: str) -> bool:
        """Check if a user has a specific relation to an object."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/check",
                json={
                    "tuple_key": {
                        "user": user,
                        "relation": relation,
                        "object": object
                    }
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("allowed", False)
                return False
        except Exception as e:
            logger.error(f"Error checking permission: {str(e)}")
            return False

    async def log_transaction(self, transaction: StoreTransaction):
        """Log and track transaction state."""
        self._transaction_state.process_transaction(transaction)

    async def is_ready(self) -> bool:
        """Check if the client is ready to handle requests."""
        return self._transaction_state.ready

    async def is_healthy(self) -> bool:
        """Check if the client is healthy."""
        return self._transaction_state.healthy

    async def full_export(self, writer: AsyncTextIOWrapper) -> None:
        """Export full state to a file."""
        policies = await self.get_policies()
        data = await self.get_data()
        await writer.write(
            json.dumps({"policies": policies, "data": data}, default=str)
        )

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        """Import full state from a file."""
        import_data = json.loads(await reader.read())
        
        for policy_id, policy_code in import_data.get("policies", {}).items():
            await self.set_policy(policy_id, policy_code)
            
        if "data" in import_data:
            await self.set_policy_data(import_data["data"])

    async def get_policy_version(self) -> Optional[str]:
        """Get the current policy version."""
        return self._policy_version

    async def set_policies(
        self,
        bundle: PolicyBundle,
        transaction_id: Optional[str] = None
    ):
        """Set policies from a bundle."""
        for policy in bundle.policy_modules:
            await self.set_policy(policy.path, policy.rego)
        self._policy_version = bundle.hash

    async def get_policy_module_ids(self) -> List[str]:
        """Get all policy module IDs."""
        policies = await self.get_policies()
        return list(policies.keys()) if policies else []