import logging
from urllib.parse import urlparse

from ddtrace import patch, tracer
from ddtrace.trace import TraceFilter
from loguru import logger


class DropRootPathTraces(TraceFilter):
    """TraceFilter that drops any trace whose root HTTP route/path is "/".

    Per ddtrace docs:
      - process_trace receives a list of spans (one trace)
      - return None to drop it, or the (optionally modified) list to keep it
    We examine only the root span (parent_id is None).
    """

    def process_trace(self, trace):
        # Locate root span
        root = next((s for s in trace if getattr(s, "parent_id", None) is None), None)
        if root is None:
            return trace  # Keep if we can't identify a root

        # Prefer normalized route (framework-provided)
        route = root.get_tag("http.route")
        if route == "/":
            return None

        # Fallback: parse raw URL if present
        url = root.get_tag("http.url")
        if url:
            try:
                if urlparse(url).path == "/":
                    return None
            except Exception:
                # Fail-open: keep the trace if parsing fails
                pass

        return trace


def configure_apm(enable_apm: bool, service_name: str):
    """Enable Datadog APM and install the DropRootPathTraces filter."""
    if not enable_apm:
        logger.info("Datadog APM disabled")
        return

    logger.info("Enabling Datadog APM")

    patch(
        fastapi=True,
        redis=True,
        asyncpg=True,
        aiohttp=True,
        loguru=True,
    )

    tracer.configure(
        trace_processors=[DropRootPathTraces()],
    )


def fix_ddtrace_logging():
    """Reduce ddtrace logger verbosity and remove its handlers so our logging
    setup controls output."""
    logging.getLogger("ddtrace").setLevel(logging.WARNING)
    ddtrace_logger = logging.getLogger("ddtrace")
    for handler in list(ddtrace_logger.handlers):
        ddtrace_logger.removeHandler(handler)
