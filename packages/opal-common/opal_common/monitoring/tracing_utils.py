from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from opal_common.config import opal_common_config
from opal_common.monitoring.tracer import get_tracer
from opentelemetry.trace import Span, set_span_in_context


@asynccontextmanager
async def start_span(
    name: str, parent: Optional[Span] = None
) -> AsyncGenerator[Optional[Span], None]:
    """Reusable async context manager for starting a span.

    Yields the span if tracing is enabled, else None.
    """
    if not opal_common_config.ENABLE_OPENTELEMETRY_TRACING:
        yield None
        return

    tracer = get_tracer()
    parent_context = set_span_in_context(parent) if parent else None
    with tracer.start_as_current_span(name, context=parent_context) as span:
        yield span
