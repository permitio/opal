import json
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp
from opal_client.callbacks.register import CallbackConfig, CallbacksRegister
from opal_client.data.fetcher import DataFetcher
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.http_utils import is_http_error_response
from opal_common.logger import logger
from opal_common.schemas.data import DataUpdateReport

GetUserDataHandler = Callable[[DataUpdateReport], Awaitable[Dict[str, Any]]]


class CallbacksReporter:
    """Can send a report to callbacks registered on the callback register."""

    def __init__(
        self, register: CallbacksRegister, data_fetcher: DataFetcher = None
    ) -> None:
        self._register = register
        self._fetcher = data_fetcher or DataFetcher()
        self._get_user_data_handler: Optional[GetUserDataHandler] = None

    async def start(self):
        await self._fetcher.start()

    async def stop(self):
        await self._fetcher.stop()

    def set_user_data_handler(self, handler: GetUserDataHandler):
        if self._get_user_data_handler is not None:
            logger.warning("set_user_data_handler called and already have a handler.")
        self._get_user_data_handler = handler

    async def report_update_results(
        self,
        report: DataUpdateReport,
        extra_callbacks: Optional[List[CallbackConfig]] = None,
    ):
        try:
            # all the urls that will be eventually called by the fetcher
            urls = []
            if self._get_user_data_handler is not None:
                report = report.copy()
                report.user_data = await self._get_user_data_handler(report)
            report_data = report.json()

            # first we add the callback urls from the callback register
            for entry in self._register.all():
                config = (
                    entry.config or HttpFetcherConfig()
                )  # should not be None if we got it from the register
                config.data = report_data
                urls.append((entry.url, config, None))

            # next we add the "one time" callbacks from extra_callbacks (i.e: callbacks sent as part of a DataUpdate message)
            if extra_callbacks is not None:
                for url, config in extra_callbacks:
                    config.data = report_data
                    urls.append((url, config, None))

            logger.info("Reporting the update to requested callbacks", urls=repr(urls))
            report_results = await self._fetcher.handle_urls(urls)
            # log reports which we failed to send
            for url, config, result in report_results:
                if isinstance(result, Exception):
                    logger.error(
                        "Failed to send report to {url}, info={exc_info}",
                        url=url,
                        exc_info=repr(result),
                    )
                if isinstance(
                    result, aiohttp.ClientResponse
                ) and is_http_error_response(
                    result
                ):  # error responses
                    try:
                        error_content = await result.json()
                    except json.JSONDecodeError:
                        error_content = await result.text()
                    logger.error(
                        "Failed to send report to {url}, got response code {status} with error: {error}",
                        url=url,
                        status=result.status,
                        error=error_content,
                    )
        except:
            logger.exception("Failed to execute report_update_results")
