import aiohttp
import json
from typing import Dict, Any

from horizon.config import OPA_SERVICE_URL
from horizon.utils import proxy_response
from horizon.enforcer.schemas import AuthorizationQuery


class OpaClient:
    """
    communicates with OPA via its REST API.
    """
    POLICY_NAME = "rbac"

    def __init__(self, opa_server_url=OPA_SERVICE_URL):
        self._opa_url = opa_server_url
        self._policy = None
        self._policy_data = None

    async def is_allowed(self, query: AuthorizationQuery):
        # opa data api format needs the input to sit under "input"
        opa_input = {
            "input": query.dict()
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._opa_url}/data/rbac/allow",
                data=json.dumps(opa_input)) as opa_response:
                return await proxy_response(opa_response)

    async def set_policy(self, policy: str):
        self._policy = policy
        async with aiohttp.ClientSession() as session:
            async with session.put(
                f"{self._opa_url}/policies/{self.POLICY_NAME}",
                data=policy,
                headers={'content-type': 'text/plain'}
            ) as opa_response:
                return await proxy_response(opa_response)

    async def set_policy_data(self, policy_data: Dict[str, Any]):
        self._policy_data = policy_data
        async with aiohttp.ClientSession() as session:
            async with session.put(
                f"{self._opa_url}/data",
                data=json.dumps(self._policy_data),
            ) as opa_response:
                return await proxy_response(opa_response)

    async def rehydrate_opa_from_process_cache(self):
        if self._policy is not None:
            await self.set_policy(self._policy)

        if self._policy_data is not None:
            await self.set_policy_data(self._policy_data)


opa = OpaClient()
