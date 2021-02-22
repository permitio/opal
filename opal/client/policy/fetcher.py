import aiohttp
import json
from typing import Dict, Tuple, List

from opal.client.config import POLICY_SERVICE_URL, CLIENT_TOKEN
from opal.client.utils import get_authorization_header
from opal.client.policy.schemas import PolicyBundle


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

    async def fetch_policy_bundle(self, directories: List[str] = ['.']) -> PolicyBundle:
        async with aiohttp.ClientSession() as session:
            params = {"path": directories}
            async with session.get(
                f"{self._backend_url}/policy",
                headers={'content-type': 'text/plain', **self._auth_headers},
                params=params
            ) as response:
                bundle = await response.json()
                return PolicyBundle(**bundle)


policy_fetcher = PolicyFetcher()


