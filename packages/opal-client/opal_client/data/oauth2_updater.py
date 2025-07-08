from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp
from aiohttp.client import ClientSession
from opal_client.logger import logger

from .updater import DefaultDataUpdater


class OAuth2DataUpdater(DefaultDataUpdater):
    async def _load_policy_data_config(
        self, url: str, headers
    ) -> aiohttp.ClientResponse:
        await self._authenticator.authenticate(headers)

        async with ClientSession(headers=headers) as session:
            response = await session.get(
                url, **self._ssl_context_kwargs, allow_redirects=False
            )

            if response.status == 307:
                return await self._load_redirected_policy_data_config(
                    response.headers["location"], headers
                )
            else:
                return response

    async def _load_redirected_policy_data_config(self, url: str, headers):
        redirect_url = self.__redirect_url(url)

        logger.info(
            "Redirecting to data-sources configuration '{source}'", source=redirect_url
        )

        async with ClientSession(headers=headers) as session:
            return await session.get(
                redirect_url, **self._ssl_context_kwargs, allow_redirects=False
            )

    def __redirect_url(self, url: str) -> str:
        u = urlparse(url)
        query = parse_qs(u.query, keep_blank_values=True)
        query.pop("token", None)
        u = u._replace(query=urlencode(query, True))

        return u.geturl()
