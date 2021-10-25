import aiohttp

from typing import List, Optional
from pydantic import ValidationError
from fastapi import status, HTTPException
from tenacity import retry, wait, stop

from opal_common.utils import get_authorization_header
from opal_common.schemas.policy import PolicyBundle
from opal_client.utils import tuple_to_dict
from opal_client.logger import logger
from opal_client.config import opal_client_config


def force_valid_bundle(bundle) -> PolicyBundle:
    try:
        return PolicyBundle(**bundle)
    except ValidationError as e:
        logger.warning("server returned invalid bundle: {err}", bundle=bundle, err=repr(e))
        raise

async def throw_if_bad_status_code(response: aiohttp.ClientResponse, expected: List[int]) -> aiohttp.ClientResponse:
        if response.status in expected:
            return response

        # else, bad status code
        details = await response.json()
        logger.warning("Unexpected response code {status}: {details}", status=response.status, details=details)
        raise ValueError(f"unexpected response code while fetching bundle: {response.status}")

class PolicyFetcher:
    """
    fetches policy from backend
    """
    DEFAULT_RETRY_CONFIG = {
        'wait': wait.wait_random_exponential(max=10),
        'stop': stop.stop_after_attempt(5),
        'reraise': True,
    }

    def __init__(self, backend_url=None, token=None, retry_config=None):
        """
        Args:
            backend_url (str): Defaults to opal_client_config.SERVER_URL.
            token ([type], optional): [description]. Defaults to opal_client_config.CLIENT_TOKEN.
        """
        self._token = token or opal_client_config.CLIENT_TOKEN
        self._backend_url = backend_url or opal_client_config.SERVER_URL
        self._auth_headers = tuple_to_dict(get_authorization_header(self._token))
        self._retry_config = retry_config if retry_config is not None else self.DEFAULT_RETRY_CONFIG
        self._policy_endpoint_url = f"{self._backend_url}/policy"

    @property
    def policy_endpoint_url(self):
        return self._policy_endpoint_url

    async def fetch_policy_bundle(
        self,
        directories: List[str] = ['.'],
        base_hash: Optional[str] = None
    ) -> Optional[PolicyBundle]:
        attempter = retry(**self._retry_config)(self._fetch_policy_bundle)
        try:
            return await attempter(directories=directories, base_hash=base_hash)
        except Exception as err:
            logger.warning("Failed all attempts to fetch bundle, got error: {err}", err=repr(err))
            raise

    async def _fetch_policy_bundle(
        self,
        directories: List[str] = ['.'],
        base_hash: Optional[str] = None
    ) -> Optional[PolicyBundle]:
        """
        Fetches the bundle. May throw, in which case we retry again.
        """
        params = {"path": directories}
        if base_hash is not None:
            params["base_hash"] = base_hash
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    self._policy_endpoint_url,
                    headers={'content-type': 'text/plain', **self._auth_headers},
                    params=params
                ) as response:
                    if response.status == status.HTTP_404_NOT_FOUND:
                        logger.warning("requested paths not found: {paths}", paths=directories)
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"requested path {self._policy_endpoint_url} was not found in the policy repo!"
                        )


                    # may throw ValueError
                    await throw_if_bad_status_code(response, expected=[status.HTTP_200_OK])

                    # may throw Validation Error
                    bundle = await response.json()
                    return force_valid_bundle(bundle)
            except aiohttp.ClientError as e:
                logger.warning("server connection error: {err}", err=repr(e))
                raise

