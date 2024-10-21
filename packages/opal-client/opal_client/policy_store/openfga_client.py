import asyncio
import json
from typing import Dict, List, Optional, Union
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
from openfga_sdk import OpenFgaClient as SDKOpenFgaClient, ClientConfiguration
from openfga_sdk.client.models import ClientWriteRequest, ClientTuple, ClientCheckRequest, ClientListObjectsRequest
from openfga_sdk.models import WriteAuthorizationModelRequest, TupleKey, ReadRequest


RETRY_CONFIG = {
    "stop": stop_after_attempt(5),
    "wait": wait_exponential(multiplier=1, min=4, max=10),
}

class OpenFGAClient(BasePolicyStoreClient):
    def __init__(
        self,
        openfga_server_url=None,
        openfga_auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        store_id: Optional[str] = None,
    ):
        base_url = openfga_server_url or opal_client_config.POLICY_STORE_URL
        self._openfga_url = base_url
        self._store_id = store_id or opal_client_config.OPENFGA_STORE_ID
        self._policy_version: Optional[str] = None
        self._lock = asyncio.Lock()
        self._token = openfga_auth_token
        self._auth_type: PolicyStoreAuth = auth_type

        self._had_successful_data_transaction = False
        self._had_successful_policy_transaction = False
        self._most_recent_data_transaction: Optional[StoreTransaction] = None
        self._most_recent_policy_transaction: Optional[StoreTransaction] = None

        configuration = ClientConfiguration(
            api_url=self._openfga_url,
            store_id=self._store_id,
        )
        if self._auth_type == PolicyStoreAuth.TOKEN:
            configuration.credentials = self._token

        self._fga_client = SDKOpenFgaClient(configuration)

    async def _get_auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._auth_type == PolicyStoreAuth.TOKEN and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @retry(**RETRY_CONFIG)
    async def set_policy(
        self,
        policy_id: str,
        policy_code: str,
        transaction_id: Optional[str] = None,
    ):
        logger.debug(f"Attempting to set policy with ID {policy_id}: {policy_code}")
        try:
            policy = json.loads(policy_code)
            response = await self._fga_client.write_authorization_model(
                WriteAuthorizationModelRequest(**policy)
            )
            self._policy_version = response.authorization_model_id
            logger.info(f"Successfully set policy with ID: {self._policy_version}")
            return response
        except json.JSONDecodeError:
            logger.error(f"Invalid policy code (not valid JSON): {policy_code}")
            raise
        except Exception as e:
            logger.error(f"Error setting policy: {str(e)}")
            raise

    @retry(**RETRY_CONFIG)
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        logger.debug(f"Attempting to set policy data: {json.dumps(policy_data, indent=2)}")
        try:
            if not policy_data:
                logger.warning("Received empty policy data. Skipping operation.")
                return None

            tuples = [
                ClientTuple(user=t["user"], relation=t["relation"], object=t["object"])
                for t in policy_data
                if all(k in t for k in ("user", "relation", "object"))
            ]
            logger.debug(f"Created tuples: {tuples}")

            if not tuples:
                logger.warning("No valid tuples found in policy data. Skipping operation.")
                return None

            body = ClientWriteRequest(writes=tuples)
            logger.debug(f"Sending write request to OpenFGA: {body}")
            await self._fga_client.write(body)
            logger.info(f"Successfully set policy data for path: {path}")
            return None
        except Exception as e:
            logger.error(f"Error setting policy data: {str(e)}")
            raise

    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        try:
            response = await self._fga_client.read_authorization_model(policy_id)
            return json.dumps(response.authorization_model.dict())
        except Exception as e:
            logger.error(f"Error getting policy: {str(e)}")
            return None

    @retry(**RETRY_CONFIG)
    async def get_policies(self) -> Optional[Dict[str, str]]:
        try:
            response = await self._fga_client.read_authorization_models()
            return {
                model.id: json.dumps(model.dict())
                for model in response.authorization_models
            }
        except Exception as e:
            logger.error(f"Error getting policies: {str(e)}")
            return None

    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        logger.warning("Deleting policies is not supported in OpenFGA")

    @retry(**RETRY_CONFIG)
    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        try:
            body = ClientWriteRequest(deletes=[ClientTuple(object=path)])
            await self._fga_client.write(body)
            logger.info(f"Successfully deleted policy data for path: {path}")
            return None
        except Exception as e:
            logger.error(f"Error deleting policy data: {str(e)}")
            raise

    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str) -> Dict:
        try:
            response = await self._fga_client.read(ReadRequest(object=path))
            return {"tuples": [tuple.dict() for tuple in response.tuples]}
        except Exception as e:
            logger.error(f"Error getting data: {str(e)}")
            return {}

    async def patch_policy_data(
        self,
        policy_data: List[Dict],
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        # OpenFGA doesn't have a direct patch operation, so we'll implement it as a write
        return await self.set_policy_data(policy_data, path, transaction_id)

    @retry(**RETRY_CONFIG)
    async def check_permission(self, user: str, relation: str, object: str) -> bool:
        try:
            response = await self._fga_client.check(
                ClientCheckRequest(user=user, relation=relation, object=object)
            )
            return response.allowed
        except Exception as e:
            logger.error(f"Error checking permission: {str(e)}")
            return False

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
        return (
            self._most_recent_policy_transaction is not None
            and self._most_recent_policy_transaction.success
        ) and (
            self._most_recent_data_transaction is not None
            and self._most_recent_data_transaction.success
        )

    async def full_export(self, writer: AsyncTextIOWrapper) -> None:
        policies = await self.get_policies()
        data = await self.get_data("")
        await writer.write(
            json.dumps({"policies": policies, "data": data}, default=str)
        )

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        import_data = json.loads(await reader.read())

        for policy_id, policy_code in import_data["policies"].items():
            await self.set_policy(policy_id, policy_code)

        await self.set_policy_data(import_data["data"])

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version

    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        for policy in bundle.policy_modules:
            await self.set_policy(policy.path, json.dumps(policy.rego))

        self._policy_version = bundle.hash