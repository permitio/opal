import aiohttp

from typing import List, Optional
from pydantic import ValidationError
from fastapi import status

from opal.common.utils import get_authorization_header
from opal.common.schemas.policy import PolicyBundle
from opal.client.utils import tuple_to_dict
from opal.client.logger import get_logger
from opal.client.config import POLICY_SERVICE_URL, CLIENT_TOKEN


logger = get_logger("opal.policy.fetcher")


def policy_bundle_or_none(bundle) -> Optional[PolicyBundle]:
    try:
        return PolicyBundle(**bundle)
    except ValidationError as e:
        logger.warn("server returned invalid bundle", bundle=bundle, err=e)
        return None


class PolicyFetcher:
    """
    fetches policy from backend
    """
    def __init__(self, backend_url=POLICY_SERVICE_URL, token=CLIENT_TOKEN):
        self._backend_url = backend_url
        self._token = token
        self._auth_headers = tuple_to_dict(get_authorization_header(token))

    async def fetch_policy_bundle(self, directories: List[str] = ['.']) -> Optional[PolicyBundle]:
        async with aiohttp.ClientSession() as session:
            params = {"path": directories}
            try:
                async with session.get(
                    f"{self._backend_url}/policy",
                    headers={'content-type': 'text/plain', **self._auth_headers},
                    params=params
                ) as response:
                    if response.status == status.HTTP_404_NOT_FOUND:
                        logger.warn("requested paths not found", paths=directories)
                        return None
                    bundle = await response.json()
                    return policy_bundle_or_none(bundle)
            except aiohttp.ClientError as e:
                logger.warn("server connection error", err=e)
                raise


policy_fetcher = PolicyFetcher()


