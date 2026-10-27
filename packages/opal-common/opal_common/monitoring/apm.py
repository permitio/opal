import logging
import os
from urllib.parse import urlparse

from ddtrace import config, patch, tracer
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


WEBSOCKET_MESSAGES_ENV = "DD_TRACE_WEBSOCKET_MESSAGES_ENABLED"


def configure_apm(enable_apm: bool, service_name: str):
    """Enable Datadog APM and install the DropRootPathTraces filter."""
    if not enable_apm:
        logger.info("Datadog APM disabled")
        return

    logger.info("Enabling Datadog APM")

    # ddtrace 4 traces every websocket message by default (3.x did not). OPAL's pub/sub runs
    # over websockets, so that would turn each published update into spans, and it logs a
    # warning with a traceback whenever a close is sent to a client that already left. Keep the
    # 3.x behaviour unless the operator chose otherwise: the env default covers integrations
    # patched below, the config assignment an ASGI integration already imported (ddtrace-run).
    operator_choice = os.environ.get(WEBSOCKET_MESSAGES_ENV)
    os.environ.setdefault(WEBSOCKET_MESSAGES_ENV, "false")

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
    if operator_choice is None:
        config.asgi.trace_asgi_websocket_messages = False


def fix_ddtrace_logging():
    """Reduce ddtrace logger verbosity and remove its handlers so our logging
    setup controls output."""
    logging.getLogger("ddtrace").setLevel(logging.WARNING)
    ddtrace_logger = logging.getLogger("ddtrace")
    for handler in list(ddtrace_logger.handlers):
        ddtrace_logger.removeHandler(handler)
