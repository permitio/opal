import asyncio
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
import aiohttp
import json
import functools
from typing import Dict, Any, Optional, List, Set

from tenacity import retry, stop_after_attempt, wait_fixed
from pydantic import BaseModel

from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_client.utils import proxy_response
from opal_common.schemas.policy import DataModule, PolicyBundle


# 2 retries with 2 seconds apart
RETRY_CONFIG = dict(wait=wait_fixed(2), stop=stop_after_attempt(2))


def fail_silently(fallback=None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except aiohttp.ClientError as e:
                return fallback
        return wrapper
    return decorator


class OpaClient(BasePolicyStoreClient):
    """
    communicates with OPA via its REST API.
    """
    POLICY_NAME = "rbac"

    def __init__(self,
                 opa_server_url=None):
        self._opa_url = opa_server_url or opal_client_config.POLICY_STORE_URL
        self._policy_data = None
        self._cached_policies: Dict[str, str] = {}
        self._policy_version: Optional[str] = None
        self._lock = asyncio.Lock()

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def set_policy(self, policy_id: str, policy_code: str):
        self._cached_policies[policy_id] = policy_code
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    f"{self._opa_url}/policies/{policy_id}",
                    data=policy_code,
                    headers={'content-type': 'text/plain'}
                ) as opa_response:
                    return await proxy_response(opa_response)
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=e)
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self._opa_url}/policies/{policy_id}",
                ) as opa_response:
                    result = await opa_response.json()
                    return result.get("result", {}).get("raw", None)
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=e)
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def delete_policy(self, policy_id: str):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.delete(
                    f"{self._opa_url}/policies/{policy_id}",
                ) as opa_response:
                    return await proxy_response(opa_response)
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=e)
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy_module_ids(self) -> List[str]:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self._opa_url}/policies",
                ) as opa_response:
                    result = await opa_response.json()
                    return OpaClient._extract_module_ids_from_policies_json(result)
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=e)
                raise

    @staticmethod
    def _extract_module_ids_from_policies_json(result: Dict[str, Any]) -> List[str]:
        modules: List[Dict[str, Any]] = result.get("result", [])
        module_ids = [module.get("id", None) for module in modules]
        module_ids = [module_id for module_id in module_ids if module_id is not None]
        return module_ids

    @fail_silently()
    async def set_policies(self, bundle: PolicyBundle):
        if bundle.old_hash is None:
            return await self._set_policies_from_complete_bundle(bundle)
        else:
            return await self._set_policies_from_delta_bundle(bundle)

    async def _set_policies_from_complete_bundle(self, bundle: PolicyBundle):
        module_ids_in_store: Set[str] = set(await self.get_policy_module_ids())
        module_ids_in_bundle: Set[str] = {module.path for module in bundle.policy_modules}
        module_ids_to_delete: Set[str] = module_ids_in_store.difference(module_ids_in_bundle)

        async with self._lock:
            # save bundled policies into store
            for module in bundle.policy_modules:
                await self.set_policy(policy_id=module.path, policy_code=module.rego)

            # save bundled policy *static* data into store
            for module in bundle.data_modules:
                await self._set_policy_data_from_bundle_data_module(module, hash=bundle.hash)

            # remove policies from the store that are not in the bundle
            # (because this bundle is "complete", i.e: contains all policy modules for a given hash)
            for module_id in module_ids_to_delete:
                await self.delete_policy(policy_id=module_id)

            # save policy version (hash) into store
            self._policy_version = bundle.hash

    async def _set_policies_from_delta_bundle(self, bundle: PolicyBundle):
        async with self._lock:
            # save bundled policies into store
            for module in bundle.policy_modules:
                await self.set_policy(policy_id=module.path, policy_code=module.rego)

            # save bundled policy *static* data into store
            for module in bundle.data_modules:
                await self._set_policy_data_from_bundle_data_module(module, hash=bundle.hash)

            # remove deleted policies (or static policy data) from store
            if bundle.deleted_files is not None:
                for module_id in bundle.deleted_files.policy_modules:
                    await self.delete_policy(policy_id=module_id)

                for module_id in bundle.deleted_files.data_modules:
                    await self.delete_policy_data(path=self._safe_data_module_path(str(module_id)))

            # save policy version (hash) into store
            self._policy_version = bundle.hash

    @classmethod
    def _safe_data_module_path(cls, path: str):
        if not path or path == ".":
            return ""

        if not path.startswith("/"):
            return f"/{path}"

        return path

    async def _set_policy_data_from_bundle_data_module(self, module: DataModule, hash: Optional[str] = None):
        module_path = self._safe_data_module_path(module.path)
        try:
            module_data = json.loads(module.data)
            return await self.set_policy_data(
                policy_data=module_data,
                path=module_path,
            )
        except json.JSONDecodeError as e:
            logger.warning(
                "bundle contains non-json data module: {module_path}",
                err=e,
                module_path=module_path,
                bundle_hash=hash
            )

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def set_policy_data(self, policy_data: Dict[str, Any], path: str = ""):
        self._policy_data = policy_data
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    f"{self._opa_url}/data{path}",
                    data=json.dumps(self._policy_data),
                ) as opa_response:
                    return await proxy_response(opa_response)
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=e)
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def delete_policy_data(self, path: str = ""):
        if not path:
            return await self.set_policy_data({})

        async with aiohttp.ClientSession() as session:
            try:
                async with session.delete(
                    f"{self._opa_url}/data{path}",
                ) as opa_response:
                    return await proxy_response(opa_response)
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=e)
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str) -> Dict:
        """
        wraps opa's "GET /data" api that extracts base data documents from opa cache.
        NOTE: opa always returns 200 and empty dict (for valid input) even if the data does not exist.

        returns a dict (parsed json).
        """
        # function accepts paths that start with / and also path that do not start with /
        if path.startswith("/"):
            path = path[1:]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self._opa_url}/data/{path}") as opa_response:
                    return await opa_response.json()
        except aiohttp.ClientError as e:
            logger.warning("Opa connection error: {err}", err=e)
            raise

    @retry(**RETRY_CONFIG)
    async def get_data_with_input(self, path: str, input: BaseModel) -> Dict:
        """
        evaluates a data document against an input.
        that is how OPA "runs queries".

        see explanation how opa evaluate documents:
        https://www.openpolicyagent.org/docs/latest/philosophy/#the-opa-document-model

        see api reference:
        https://www.openpolicyagent.org/docs/latest/rest-api/#get-a-document-with-input
        """
        # opa data api format needs the input to sit under "input"
        opa_input = {
            "input": input.dict()
        }
        if path.startswith("/"):
            path = path[1:]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._opa_url}/data/{path}",
                    data=json.dumps(opa_input)
                ) as opa_response:
                    return await proxy_response(opa_response)
        except aiohttp.ClientError as e:
            logger.warning("Opa connection error: {err}", err=e)
            raise
