from opentelemetry import trace
from opentelemetry.trace import NoOpTracer

_tracer = None


def init_tracer(tracer_provider=None):
    global _tracer
    if tracer_provider is not None:
        _tracer = tracer_provider.get_tracer(__name__)
    else:
        _tracer = trace.get_tracer(__name__)


def get_tracer():
    if _tracer is None:
        return NoOpTracer()
    return _tracer
