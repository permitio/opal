from opentelemetry import metrics
from opentelemetry.metrics import NoOpMeter

_meter = None


def init_meter(meter_provider=None):
    global _meter
    if meter_provider is not None:
        _meter = meter_provider.get_meter(__name__)
    else:
        _meter = metrics.get_meter(__name__)


def get_meter():
    if _meter is None:
        return NoOpMeter()
    return _meter
