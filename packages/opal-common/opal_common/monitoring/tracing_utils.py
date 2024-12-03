from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from opal_common.config import opal_common_config
from opal_common.monitoring.tracer import get_tracer
from opentelemetry.trace import Span

@asynccontextmanager
async def start_span(name: str) -> AsyncGenerator[Optional[Span], None]:
    """
    Reusable async context manager for starting a span.
    Yields the span if tracing is enabled, else None.
    """
    if not opal_common_config.ENABLE_OPENTELEMETRY_TRACING:
        yield None
        return

    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        yield span