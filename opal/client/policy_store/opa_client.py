import asyncio
import aiohttp
import json
import functools
from typing import Dict, Any

from tenacity import retry, stop_after_attempt, wait_fixed

from opal.client.config import POLICY_STORE_URL
from opal.client.logger import get_logger
from opal.client.utils import proxy_response
from opal.client.enforcer.schemas import AuthorizationQuery
from opal.common.schemas.policy import PolicyBundle

logger = get_logger("Opa Client")

# 2 retries with 2 seconds apart
RETRY_CONFIG = dict(wait=wait_fixed(2), stop=stop_after_attempt(2))
IS_ALLOWED_FALLBACK = dict(result=dict(allow=False, debug="OPA not responding"))

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

class OpaClient:
    """
    communicates with OPA via its REST API.
    """
    POLICY_NAME = "rbac"

    def __init__(self, opa_server_url=POLICY_STORE_URL):
        self._opa_url = opa_server_url
        self._policy_data = None

    # by default, if OPA is down, authorization is denied
    @fail_silently(fallback=IS_ALLOWED_FALLBACK)
    @retry(**RETRY_CONFIG)
    async def is_allowed(self, query: AuthorizationQuery):
        # opa data api format needs the input to sit under "input"
        opa_input = {
            "input": query.dict()
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._opa_url}/data/rbac",
                    data=json.dumps(opa_input)) as opa_response:
                    return await proxy_response(opa_response)
        except aiohttp.ClientError as e:
            logger.warn("Opa connection error", err=e)
            raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def set_policy(self, policy_id: str, policy_code: str):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    f"{self._opa_url}/policies/{policy_id}",
                    data=policy_code,
                    headers={'content-type': 'text/plain'}
                ) as opa_response:
                    return await proxy_response(opa_response)
            except aiohttp.ClientError as e:
                logger.warn("Opa connection error", err=e)
                raise

    @fail_silently()
    async def set_policies(self, bundle: PolicyBundle):
        lock = asyncio.Lock()
        async with lock:
            for module in bundle.rego_modules:
                await self.set_policy(policy_id=module.path, policy_code=module.rego)

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def set_policy_data(self, policy_data: Dict[str, Any], path=""):
        self._policy_data = policy_data
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    f"{self._opa_url}/data{path}",
                    data=json.dumps(self._policy_data),
                ) as opa_response:
                    return await proxy_response(opa_response)
            except aiohttp.ClientError as e:
                logger.warn("Opa connection error", err=e)
                raise

    async def rehydrate_opa_from_process_cache(self):
        if self._policy is not None:
            await self.set_policy(self._policy)

        if self._policy_data is not None:
            await self.set_policy_data(self._policy_data)

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str):
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
            logger.warn("Opa connection error", err=e)
            raise

