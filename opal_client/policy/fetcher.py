import aiohttp

from typing import List, Optional
from pydantic import ValidationError
from fastapi import status

from opal_common.utils import get_authorization_header
from opal_common.schemas.policy import PolicyBundle
from opal_client.utils import tuple_to_dict
from opal_client.logger import logger
from opal_client.config import opal_client_config


def policy_bundle_or_none(bundle) -> Optional[PolicyBundle]:
    try:
        return PolicyBundle(**bundle)
    except ValidationError as e:
        logger.warning("server returned invalid bundle: {err}", bundle=bundle, err=e)
        return None


class PolicyFetcher:
    """
    fetches policy from backend
    """
    def __init__(self, backend_url=None, token=None):
        """
        Args:
            backend_url ([type], optional): Defaults to opal_client_config.SERVER_URL.
            token ([type], optional): [description]. Defaults to opal_client_config.CLIENT_TOKEN.
        """
        self._backend_url = backend_url or opal_client_config.SERVER_URL
        self._token = token or opal_client_config.CLIENT_TOKEN
        self._auth_headers = tuple_to_dict(get_authorization_header(self._token))

    async def fetch_policy_bundle(
        self,
        directories: List[str] = ['.'],
        base_hash: Optional[str] = None
    ) -> Optional[PolicyBundle]:
        params = {"path": directories}
        if base_hash is not None:
            params["base_hash"] = base_hash
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self._backend_url}/policy",
                    headers={'content-type': 'text/plain', **self._auth_headers},
                    params=params
                ) as response:
                    if response.status == status.HTTP_404_NOT_FOUND:
                        logger.warning("requested paths not found: {paths}", paths=directories)
                        return None
                    bundle = await response.json()
                    return policy_bundle_or_none(bundle)
            except aiohttp.ClientError as e:
                logger.warning("server connection error: {err}", err=e)
                raise


policy_fetcher = PolicyFetcher()
