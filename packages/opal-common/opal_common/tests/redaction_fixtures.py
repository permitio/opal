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


@contextmanager
def capture_logs() -> Iterator[CapturedLogs]:
    """Captures loguru output in both forms OPAL can write it.

    Neither sink runs the scrubbing patcher or stream wrapper installed by
    ``configure_logs``, so what is captured is what the call site itself
    emits. ``diagnose`` is off, as in OPAL's default config.
    """
    logs = CapturedLogs()
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
