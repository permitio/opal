"""One place that decides how opal-server's DogStatsD client is configured.

Both the worker app (``OpalServer._configure_monitoring``) and the gunicorn
MASTER (the pre-fork scope preload in ``scopes/task.py``, run from
``scripts/gunicorn_conf.py:when_ready`` before any worker exists) must call
this: the master emits git metrics during preload, and until 0.9.9-rc.3 it
never configured the client, so those metrics reached Datadog WITHOUT the
``permit.opal`` namespace (``opal_server.scopes.git_ops_in_flight`` next to the
workers' ``permit.opal.opal_server.scopes.git_ops_in_flight``) — invisible to
every dashboard and monitor written against the namespaced names.
"""
import os

from opal_common.config import opal_common_config
from opal_common.monitoring import metrics

STATSD_PORT = 8125
METRICS_NAMESPACE = "opal"


def configure_server_metrics() -> None:
    """Configure (or re-configure) the process-wide DogStatsD client the way
    opal-server expects it: fail-silent when metrics are disabled, namespace
    ``permit.opal`` and the agent host from ``DD_AGENT_HOST`` when enabled.
    Safe to call more than once (a forked worker configures again at app
    startup)."""
    metrics.configure_metrics(
        enable_metrics=opal_common_config.ENABLE_METRICS,
        statsd_host=os.environ.get("DD_AGENT_HOST", "localhost"),
        statsd_port=STATSD_PORT,
        namespace=METRICS_NAMESPACE,
    )
