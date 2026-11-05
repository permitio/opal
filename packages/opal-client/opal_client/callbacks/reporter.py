import json
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp
from opal_client.callbacks.register import CallbackConfig, CallbacksRegister
from opal_client.data.fetcher import DataFetcher
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.http_utils import is_http_error_response, redact_url
from opal_common.logger import logger
from opal_common.logging_utils.errors import describe_error
from opal_common.schemas.data import DataUpdateReport

GetUserDataHandler = Callable[[DataUpdateReport], Awaitable[Dict[str, Any]]]

# Each entry's fetcher ``config`` (auth headers) and inline ``data`` stay out of
# the payload sent to callbacks.
_CALLBACK_PAYLOAD_EXCLUDE = {"reports": {"__all__": {"entry": {"config", "data"}}}}


def build_callback_payload(report: DataUpdateReport) -> str:
    """Serializes a report into the JSON body POSTed to callback urls.

    Each entry's ``config`` and ``data`` are omitted rather than nulled, since
    receivers may declare them with non-null defaults (e.g. ``config: dict =
    {}``), and each entry's url is passed through ``redact_url``. Every other
    field - including subclass-only entry fields - is kept, and the result still
    parses as a ``DataUpdateReport``.
    """
    payload = report.model_dump(mode="json", exclude=_CALLBACK_PAYLOAD_EXCLUDE)
    for entry_report in payload["reports"]:
        entry = entry_report["entry"]
        entry["url"] = redact_url(entry["url"])
    # compact and UTF-8, like model_dump_json()
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


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
            # all callback request tuples (url, config, None) that will be eventually called by the fetcher
            callback_requests = []
            if self._get_user_data_handler is not None:
                report = report.model_copy()
                report.user_data = await self._get_user_data_handler(report)
            report_data = build_callback_payload(report)

            # Each request gets its own copy of the config carrying the report: the
            # registered configs are shared (GET /callbacks serves them, and
            # DEFAULT_UPDATE_CALLBACK_CONFIG backs every url-only callback).

            # first we add the callback urls from the callback register
            for entry in self._register.all():
                config = (
                    entry.config or HttpFetcherConfig()
                )  # should not be None if we got it from the register
                callback_requests.append(
                    (entry.url, config.model_copy(update={"data": report_data}), None)
                )

            # next we add the "one time" callbacks from extra_callbacks (i.e: callbacks sent as part of a DataUpdate message)
            if extra_callbacks is not None:
                for url, config in extra_callbacks:
                    callback_requests.append(
                        (url, config.model_copy(update={"data": report_data}), None)
                    )

            # log only the URLs — FetcherConfig may carry Authorization headers and the full report payload.
            # Callback URLs are user-supplied and can embed credentials, so redact them too.
            urls = [redact_url(request[0]) for request in callback_requests]
            logger.info("Reporting the update to requested callbacks", urls=urls)
            report_results = await self._fetcher.handle_urls(callback_requests)
            # log reports which we failed to send
            for url, config, result in report_results:
                if isinstance(result, Exception):
                    logger.error(
                        "Failed to send report to {url}, info={exc_info}",
                        url=redact_url(url),
                        exc_info=describe_error(result),
                    )
                if isinstance(
                    result, aiohttp.ClientResponse
                ) and is_http_error_response(
                    result
                ):  # error responses
                    # Not necessarily JSON (e.g. an HTML page from a proxy), and
                    # result.json() would raise ContentTypeError for it.
                    body = await result.text(errors="replace")
                    try:
                        error_content = json.loads(body)
                    except json.JSONDecodeError:
                        error_content = body
                    logger.error(
                        "Failed to send report to {url}, got response code {status} with error: {error}",
                        url=redact_url(url),
                        status=result.status,
                        error=error_content,
                    )
        except Exception:
            logger.exception("Failed to execute report_update_results")
