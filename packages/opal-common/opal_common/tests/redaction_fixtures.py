"""Shared helpers for tests asserting that sensitive values stay out of logs,
wire payloads and error text."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Type

import aiohttp
from loguru import logger
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL


@dataclass
class CapturedLogs:
    #: Records rendered with loguru's default format (traceback included).
    text: List[str] = field(default_factory=list)
    #: Records as a ``serialize=True`` sink writes them - ``extra`` included,
    #: so a keyword argument the message does not reference still shows up.
    serialized: List[str] = field(default_factory=list)

    @property
    def combined(self) -> str:
        return "\n".join(self.text + self.serialized)


def _no_patching(record) -> None:
    pass


@contextmanager
def without_log_patcher() -> Iterator[None]:
    """Disables loguru's global patcher, restoring the previous one on exit.

    ``configure_logs`` installs a patcher that masks credentials in every
    record before any sink sees it, and it stays installed for the rest of
    the process: once any test has built an OpalServer or OpalClient, a sink
    added later only ever sees masked records, and a test could pass without
    the call-site fix it is meant to check.
    """
    previous = logger._core.patcher
    logger.configure(patcher=_no_patching)
    try:
        yield
    finally:
        # configure() ignores patcher=None, so restore the attribute itself
        logger._core.patcher = previous


@contextmanager
def capture_logs() -> Iterator[CapturedLogs]:
    """Captures loguru output in both forms OPAL can write it.

    The global patcher ``configure_logs`` installs is disabled while capturing
    (see ``without_log_patcher``), and neither sink is wrapped in its scrubbing
    stream, so what is captured is what the call site itself emits.
    ``diagnose`` is off, as in OPAL's default config.
    """
    logs = CapturedLogs()
    with without_log_patcher():
        sink_ids = [
            logger.add(logs.text.append, level="DEBUG", colorize=False, diagnose=False),
            logger.add(logs.serialized.append, level="DEBUG", serialize=True),
        ]
        try:
            yield logs
        finally:
            for sink_id in sink_ids:
                logger.remove(sink_id)


def response_error(
    headers: Dict[str, str],
    url: str = "http://example.com/v1/data",
    error_type: Type[aiohttp.ClientResponseError] = aiohttp.ClientResponseError,
    status: int = 502,
) -> aiohttp.ClientResponseError:
    """An aiohttp response error for a request sent with ``headers``.

    Its ``repr()`` - unlike its ``str()`` - renders those headers.
    """
    request_info = aiohttp.RequestInfo(
        URL(url), "GET", CIMultiDictProxy(CIMultiDict(headers)), URL(url)
    )
    return error_type(request_info, (), status=status, message="Bad Gateway")
