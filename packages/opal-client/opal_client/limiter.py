import aiohttp
from fastapi import HTTPException, status
from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_common.security.sslcontext import get_custom_ssl_context
from opal_common.utils import get_authorization_header, tuple_to_dict
from tenacity import retry, stop, wait_random_exponential


class StartupLoadLimiter:
    """Validates OPAL server is not too loaded before starting up."""

    def __init__(self, backend_url=None, token=None):
        """
        Args:
            backend_url (str): Defaults to opal_client_config.SERVER_URL.
            token ([type], optional): [description]. Defaults to opal_client_config.CLIENT_TOKEN.
        """
        self._backend_url = backend_url or opal_client_config.SERVER_URL
        self._loadlimit_endpoint_url = f"{self._backend_url}/loadlimit"

        self._token = token or opal_client_config.CLIENT_TOKEN
        self._auth_headers = tuple_to_dict(get_authorization_header(self._token))
        self._custom_ssl_context = get_custom_ssl_context()
        self._ssl_context_kwargs = (
            {"ssl": self._custom_ssl_context}
            if self._custom_ssl_context is not None
            else {}
        )

    @retry(wait=wait_random_exponential(max=10), stop=stop.stop_never, reraise=True)
    async def wait_for_server_ready(self):
        logger.info("Trying to get server's load limit pass")
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    self._loadlimit_endpoint_url,
                    headers={"content-type": "text/plain", **self._auth_headers},
                    **self._ssl_context_kwargs,
                ) as response:
                    if response.status != status.HTTP_200_OK:
                        logger.warning(
                            f"loadlimit endpoint returned status {response.status}"
                        )
                        raise HTTPException(response.status)
            except aiohttp.ClientError as e:
                logger.warning("server connection error: {err}", err=repr(e))
                raise

    def __call__(self):
        return self.wait_for_server_ready()
