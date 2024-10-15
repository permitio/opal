import logging
from typing import Optional
from urllib.parse import urlparse

from ddtrace import Span, config, patch, tracer
from ddtrace.filters import TraceFilter
from loguru import logger


def configure_apm(enable_apm: bool, service_name: str):
    """Optionally enable datadog APM / profiler."""
    if enable_apm:
        logger.info("Enabling DataDog APM")
        # logging.getLogger("ddtrace").propagate = False

        class FilterRootPathTraces(TraceFilter):
            def process_trace(self, trace: list[Span]) -> Optional[list[Span]]:
                for span in trace:
                    if span.parent_id is not None:
                        return trace

                    if url := span.get_tag("http.url"):
                        parsed_url = urlparse(url)

                        if parsed_url.path == "/":
                            return None

                return trace

        patch(
            fastapi=True,
            redis=True,
            asyncpg=True,
            aiohttp=True,
            loguru=True,
        )
        tracer.configure(
            settings={
                "FILTERS": [
                    FilterRootPathTraces(),
                ]
            }
        )

    else:
        logger.info("DataDog APM disabled")
        tracer.configure(enabled=False)


def fix_ddtrace_logging():
    logging.getLogger("ddtrace").setLevel(logging.WARNING)

    ddtrace_logger = logging.getLogger("ddtrace")
    for handler in ddtrace_logger.handlers:
        ddtrace_logger.removeHandler(handler)
