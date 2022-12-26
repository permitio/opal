import os

import datadog
from loguru import logger


def configure_metrics(
    enable_metrics: bool, statsd_host: str, statsd_port: int, namespace: str = ""
):
    if not enable_metrics:
        logger.info("DogStatsD metrics disabled")
        return
    else:
        logger.info(
            "DogStatsD metrics enabled; statsd: {host}:{port}",
            host=statsd_host,
            port=statsd_port,
        )

    if not namespace:
        namespace = os.environ.get("DD_SERVICE", "")

    namespace = namespace.lower().replace("-", "_")
    datadog.initialize(
        statsd_host=statsd_host,
        statsd_port=statsd_port,
        statsd_namespace=f"permit.{namespace}",
    )


def increment(metric: str, tags: dict[str, str] = None):
    datadog.statsd.increment(metric, tags=tags)


def decrement(metric: str, tags: dict[str, str] = None):
    datadog.statsd.decrement(metric, tags=tags)


def gauge(metric: str, value: float, tags: dict[str, str] = None):
    datadog.statsd.gauge(metric, value, tags=tags)
