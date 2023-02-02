import os
from typing import Optional

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


def _format_tags(tags: Optional[dict[str, str]]) -> Optional[list[str]]:
    if not tags:
        return None

    return [f"{k}:{v}" for k, v in tags.items()]


def increment(metric: str, tags: Optional[dict[str, str]] = None):
    datadog.statsd.increment(metric, tags=_format_tags(tags))


def decrement(metric: str, tags: Optional[dict[str, str]] = None):
    datadog.statsd.decrement(metric, tags=_format_tags(tags))


def gauge(metric: str, value: float, tags: Optional[dict[str, str]] = None):
    datadog.statsd.gauge(metric, value, tags=_format_tags(tags))


def event(title: str, message: str, tags: Optional[dict[str, str]] = None):
    datadog.statsd.event(title=title, message=message, tags=_format_tags(tags))
