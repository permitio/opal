import aiohttp
import json
from typing import Dict, Any, Tuple

from opal.client.config import POLICY_SERVICE_URL, CLIENT_TOKEN
from opal.client.utils import proxy_response, get_authorization_header
from opal.client.enforcer.schemas import AuthorizationQuery


def tuple_to_dict(tup: Tuple[str, str]) -> Dict[str, str]:
    return dict([tup])


class PolicyFetcher:
    """
    fetches policy from backend
    """
    def __init__(self, backend_url=POLICY_SERVICE_URL, token=CLIENT_TOKEN):
        self._backend_url = backend_url
        self._token = token
        self._auth_headers = tuple_to_dict(get_authorization_header(token))

    async def fetch_policy(self) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self._backend_url}/policy",
                headers={'content-type': 'text/plain', **self._auth_headers}
            ) as response:
                return await response.text()

    async def fetch_policy_data(self) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self._backend_url}/policy-config",
                headers=self._auth_headers
            ) as response:
                return await response.json()


policy_fetcher = PolicyFetcher()


