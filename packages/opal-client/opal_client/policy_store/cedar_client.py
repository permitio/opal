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


class CedarClient(BasePolicyStoreClient):
    def __init__(
        self,
        cedar_server_url=None,
        cedar_auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
    ):
        base_url = cedar_server_url or opal_client_config.POLICY_STORE_URL
        self._cedar_url = f"{base_url}/v1"
        self._policy_version: Optional[str] = None
        self._lock = asyncio.Lock()
        self._token = cedar_auth_token
        self._auth_type: PolicyStoreAuth = auth_type

        self._had_successful_data_transaction = False
        self._had_successful_policy_transaction = False
        self._most_recent_data_transaction: Optional[StoreTransaction] = None
        self._most_recent_policy_transaction: Optional[StoreTransaction] = None

        if auth_type == PolicyStoreAuth.TOKEN:
            if self._token is None:
                logger.error("POLICY_STORE_AUTH_TOKEN can not be empty")
                raise TypeError("required variables for token auth are not set")
        elif auth_type == PolicyStoreAuth.OAUTH:
            raise ValueError("Cedar doesn't support OAuth.")

        logger.info(f"Authentication mode for policy store: {auth_type}")

    async def _get_auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._auth_type == PolicyStoreAuth.TOKEN and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy(
        self,
        policy_id: str,
        policy_code: str,
        transaction_id: Optional[str] = None,
    ):
        # ignore explicitly configured paths
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring setting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return
        async with aiohttp.ClientSession() as session:
            try:
                headers = await self._get_auth_headers()
                async with session.put(
                    f"{self._cedar_url}/policies/{quote_plus(policy_id)}",
                    json={
                        "content": policy_code,
                    },
                    headers=headers,
                ) as cedar_response:
                    return await proxy_response_unless_invalid(
                        cedar_response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_400_BAD_REQUEST,  # No point in immediate retry, this means erroneous policy (bad syntax, duplicated definition, etc)
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning("Cedar Agent connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        async with aiohttp.ClientSession() as session:
            try:
                headers = await self._get_auth_headers()

                async with session.get(
                    f"{self._cedar_url}/policies/{quote_plus(policy_id)}",
                    headers=headers,
                ) as cedar_response:
                    result = await cedar_response.json()
                    return result.get("result", {}).get("raw", None)
            except aiohttp.ClientError as e:
                logger.warning("Cedar Agent connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policies(self) -> Optional[Dict[str, str]]:
        async with aiohttp.ClientSession() as session:
            try:
                headers = await self._get_auth_headers()

                async with session.get(
                    f"{self._cedar_url}/policies", headers=headers
                ) as cedar_response:
                    result = await cedar_response.json()
                    return {policy["id"]: policy["content"] for policy in result}
            except aiohttp.ClientError as e:
                logger.warning("Cedar Agent connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        # ignore explicitly configured paths
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring deleting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return

        async with aiohttp.ClientSession() as session:
            try:
                headers = await self._get_auth_headers()

                async with session.delete(
                    f"{self._cedar_url}/policies/{quote_plus(policy_id)}",
                    headers=headers,
                ) as cedar_response:
                    return await proxy_response_unless_invalid(
                        cedar_response,
                        accepted_status_codes=[
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_404_NOT_FOUND,
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning("Cedar Agent connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        if path != "":
            raise ValueError("Cedar can only change the entire data structure at once.")

        if not isinstance(policy_data, list):
            logger.warning(
                "OPAL client was instructed to put something that is not a list on Cedar. This will probably not work."
            )

        async with aiohttp.ClientSession() as session:
            try:
                headers = await self._get_auth_headers()
                async with session.put(
                    f"{self._cedar_url}/data",
                    json=policy_data,
                    headers=headers,
                ) as cedar_response:
                    response = await proxy_response_unless_invalid(
                        cedar_response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_304_NOT_MODIFIED,
                        ],
                    )
                    return response
            except aiohttp.ClientError as e:
                logger.warning("Cedar Agent connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        if path != "":
            raise ValueError("Cedar can only change the entire data structure at once.")

        async with aiohttp.ClientSession() as session:
            try:
                headers = await self._get_auth_headers()

                async with session.delete(
                    f"{self._cedar_url}/data", headers=headers
                ) as cedar_response:
                    response = await proxy_response_unless_invalid(
                        cedar_response,
                        accepted_status_codes=[
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_404_NOT_FOUND,
                        ],
                    )
                    return response
            except aiohttp.ClientError as e:
                logger.warning("Cedar Agent connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str) -> Dict:
        """
        wraps opa's "GET /data" api that extracts base data documents from opa cache.
        NOTE: opa always returns 200 and empty dict (for valid input) even if the data does not exist.

        returns a dict (parsed json).
        """
        if path != "":
            raise ValueError("Cedar can only change the entire data structure at once.")
        try:
            headers = await self._get_auth_headers()

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._cedar_url}/data", headers=headers
                ) as cedar_response:
                    json_response = await cedar_response.json()
                    return json_response
        except aiohttp.ClientError as e:
            logger.warning("Cedar Agent connection error: {err}", err=repr(e))
            raise

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

        for id, raw in import_data["policies"].items():
            self.set_policy(policy_id=id, policy_code=raw)

        await self.set_policy_data(import_data["data"])

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version

    @affects_transaction
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        for policy in bundle.policy_modules:
            await self.set_policy(policy.path, policy.rego)

        deleted_modules: Union[List[str], Set[str]] = []

        if bundle.old_hash is None:
            deleted_modules = set((await self.get_policies()).keys()) - set(
                policy.path for policy in bundle.policy_modules
            )
        elif bundle.deleted_files is not None:
            deleted_modules = [
                str(module) for module in bundle.deleted_files.policy_modules
            ]

        for module_id in deleted_modules:
            print(module_id)
            await self.delete_policy(policy_id=module_id)
        self._policy_version = bundle.hash
