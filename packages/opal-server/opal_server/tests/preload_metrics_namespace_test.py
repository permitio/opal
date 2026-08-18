"""P1 (PR3 fixes): metrics emitted by the gunicorn MASTER during the pre-fork
scope preload must carry the same ``permit.opal`` namespace as the workers'.

Observed after the 0.9.9-rc.2 staging rollout: ``opal_server.scopes.count`` /
``opal_server.scopes.git_ops_in_flight{pid:<master>}`` next to the workers'
``permit.opal.opal_server.scopes.*`` — the master never configured the
DogStatsD client, so its gauges went out bare and no dashboard/monitor built on
the namespaced names could see the boot phase.
"""
import datadog
import pytest
from opal_common.config import opal_common_config
from opal_common.monitoring import metrics
from opal_server import metrics_setup
from opal_server.scopes import task as task_module
from opal_server.config import opal_server_config


@pytest.fixture
def statsd_reset(monkeypatch):
    """Isolate the process-wide client: fresh namespace before, restore after."""
    saved_ns = datadog.statsd.namespace
    datadog.statsd.namespace = None
    yield
    datadog.statsd.namespace = saved_ns


def test_configure_server_metrics_sets_the_permit_opal_namespace(monkeypatch, statsd_reset):
    monkeypatch.setattr(opal_common_config, "ENABLE_METRICS", True)
    metrics_setup.configure_server_metrics()
    assert datadog.statsd.namespace == "permit.opal"


def test_configure_server_metrics_is_fail_silent_when_disabled(monkeypatch, statsd_reset):
    monkeypatch.setattr(opal_common_config, "ENABLE_METRICS", False)
    metrics_setup.configure_server_metrics()
    assert datadog.statsd.namespace is None, "disabled metrics must not touch the client"


def test_gauge_after_configure_is_namespaced_on_the_wire(monkeypatch, statsd_reset):
    """The property the dashboards depend on: the serialized packet name."""
    monkeypatch.setattr(opal_common_config, "ENABLE_METRICS", True)
    metrics_setup.configure_server_metrics()
    payloads = []
    orig = datadog.statsd._serialize_metric

    def record(*a, **k):
        p = orig(*a, **k)
        payloads.append(p)
        return p

    monkeypatch.setattr(datadog.statsd, "_serialize_metric", record)
    monkeypatch.setattr(datadog.statsd, "_send_to_server", lambda payload: None)
    monkeypatch.setattr(datadog.statsd, "_send_to_buffer", lambda payload: None)
    datadog.statsd.disable_aggregation()
    metrics.gauge("opal_server.scopes.count", 593)
    assert payloads and payloads[-1].startswith(
        "permit.opal.opal_server.scopes.count:593|g"
    ), payloads


def test_preload_configures_metrics_before_syncing(monkeypatch):
    """The master's preload path is the one that was missing it: it must
    configure the client BEFORE the first sync emits anything."""
    order = []
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(
        task_module, "configure_server_metrics", lambda: order.append("configure")
    )

    class _FakeService:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            order.append("sync")

    monkeypatch.setattr(task_module, "ScopesService", _FakeService)
    monkeypatch.setattr(task_module, "RedisDB", lambda url: object())
    monkeypatch.setattr(task_module, "ScopeRepository", lambda db: object())
    monkeypatch.setattr(task_module, "drain_git_ops", lambda t: True)
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(task_module.GitPolicyFetcher, "reset_caches", staticmethod(lambda: None))

    task_module.ScopesPolicyWatcherTask.preload_scopes()

    assert order == ["configure", "sync"], order
