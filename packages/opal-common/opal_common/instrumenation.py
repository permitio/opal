from typing import Optional
from urllib.parse import urlparse

from ddtrace import Span, patch, tracer
from ddtrace.filters import TraceFilter
from loguru import logger


def instrument_app(
    enable_apm: bool = False,
    enable_profiler: bool = False,
    enable_runtime_metrics: bool = False,
):
    """optionally enable datadog APM / profiler."""
    # enable datadog APM (tracing)
    if enable_apm:
        logger.info("Enabling DataDog APM")

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

        patch(fastapi=True, redis=True, asyncpg=True, aiohttp=True, celery=True)
        tracer.configure(
            settings={
                "FILTERS": [
                    FilterRootPathTraces(),
                ]
            }
        )
    else:
        logger.info("DataDog APM disabled")
        tracer.enabled = False

    # enable datadog profiler
    if enable_profiler:
        logger.info("enabling datadog profiler")
        from ddtrace.profiling import Profiler

        prof = Profiler()
        prof.start()

        from ddtrace.runtime import RuntimeMetrics

        RuntimeMetrics.enable()
    else:
        logger.info("DataDog profiling disabled")

    if enable_runtime_metrics:
        logger.info("enabling datadog runtime metrics")

        from ddtrace.runtime import RuntimeMetrics

        RuntimeMetrics.enable()
    else:
        logger.info("DataDog runtime metrics disabled")
