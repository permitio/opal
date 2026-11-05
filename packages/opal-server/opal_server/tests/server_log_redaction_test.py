"""Log sites in opal-server must redact auth.

Covers auth carried in URLs, client reports, git errors and RPC payloads.
Tests that log check a text sink and a ``serialize=True`` sink: loguru keeps
bound kwargs in ``record["extra"]``, which the JSON sink prints verbatim. They
capture with the patcher ``configure_logs`` installs disabled, so they see what
the call site itself emits; the data-router route tests also run with it on. The
``_report_for_log`` tests call that helper directly.
"""

import json
import logging
import re
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi_websocket_rpc.logger import get_logger as get_rpc_library_logger
from loguru import logger
from opal_common.logger import _scrub_record_message
from opal_common.logging_utils.intercept import InterceptHandler
from opal_common.schemas.data import DataUpdateReport, ServerDataSourceConfig
from opal_common.tests.log_capture import starting_with
from opal_common.tests.redaction_fixtures import (
    CapturedLogs,
    capture_logs,
    without_log_patcher,
)
from opal_common.urls import set_url_query_param
from opal_server import server as server_module
from opal_server.config import opal_server_config
from opal_server.data import api as data_api
from opal_server.policy.watcher import task as watcher_task_module
from opal_server.redis_utils import RedisDB

FAKE_USER = "fakeuser"
FAKE_KEY = "FAKE-KEY-123"
FAKE_PASSWORD = "fakepass-FAKE-456"
FAKE_HEADER = "Bearer FAKE-KEY-789"
FAKE_DATA = "FAKE-DATA-PAYLOAD"
CLIENT_JWT = "fake.client.jwt-abcdefghij"

REPORT_URL = (
    f"https://{FAKE_USER}:{FAKE_PASSWORD}@data.example.com/v1"
    f"?token={FAKE_KEY}&region=eu"
)
REDACTED_REPORT_URL = "https://***@data.example.com/v1?token=***&region=eu"

PATCHER_STATES = pytest.mark.parametrize(
    "scrub", [False, True], ids=["patcher-off", "patcher-on"]
)


@contextmanager
def _captured_logs() -> Iterator[Tuple[List[str], List[str]]]:
    with capture_logs() as logs:
        yield logs.text, logs.serialized


@contextmanager
def _captured_logs_with_patcher(scrub: bool) -> Iterator[CapturedLogs]:
    """Captures as ``capture_logs`` does, with the production patcher on
    (``scrub``) or off.

    ``capture_logs`` restores the previous patcher on exit either way.
    """
    with capture_logs() as logs:
        if scrub:
            logger.configure(patcher=_scrub_record_message)
        yield logs


def _records(serialized: List[str], prefix: str) -> List[Dict[str, Any]]:
    return starting_with([json.loads(line)["record"] for line in serialized], prefix)


def _single_record(logs: CapturedLogs, phrase: str) -> Dict[str, Any]:
    """The one record holding ``phrase``, which each sink must have
    received."""
    assert sum(phrase in line for line in logs.text) == 1, logs.text
    records = _records(logs.serialized, phrase)
    assert len(records) == 1, logs.serialized
    return records[0]


def _assert_sinks_healthy(
    capfd: pytest.CaptureFixture[str], sink_ids: List[int]
) -> None:
    """None of the given sinks failed (loguru prints the failure to stderr and
    drops the record).

    Keyed by handler id, since handlers other tests leave behind may
    report their own failures.
    """
    assert sink_ids
    err = capfd.readouterr().err
    for sink_id in sink_ids:
        assert f"Logging error in Loguru Handler #{sink_id} ---" not in err, err


def _assert_absent(values, *outputs: List[str]):
    for output in outputs:
        joined = "\n".join(output)
        for value in values:
            assert value not in joined, joined


class FakeAuthenticator:
    def __call__(self):
        return {}


def _client(data_sources_config: ServerDataSourceConfig) -> TestClient:
    router = data_api.init_data_updates_router(
        None, data_sources_config, FakeAuthenticator()
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _report_payload(*urls: str) -> Dict[str, Any]:
    return {
        "update_id": "fake-update",
        "policy_hash": "fake-policy-hash",
        "user_data": {"tenant": "t-1"},
        "reports": [
            {
                "entry": {
                    "url": url,
                    "config": {"headers": {"Authorization": FAKE_HEADER}},
                    "data": {"k": FAKE_DATA},
                    "topics": ["policy_data"],
                },
                "fetched": True,
                "saved": True,
                "hash": "fake-entry-hash",
            }
            for url in urls
        ],
    }


def _rendered_urls(*urls: str) -> List[str]:
    report = DataUpdateReport.model_validate(_report_payload(*urls))
    rendered = data_api._report_for_log(report)
    return [entry_report["entry"]["url"] for entry_report in rendered["reports"]]


# --- Redis URL (S3) ---------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_connect_log_masks_password():
    with _captured_logs() as (text, serialized):
        RedisDB(f"redis://fakeuser:{FAKE_PASSWORD}@redis.example.com:6379/0")

    assert any("Connecting to Redis" in line for line in text), text
    assert any(
        re.search(r"redis://\*\*\*@redis\.example\.com:6379", line)
        for line in serialized
    ), serialized
    _assert_absent([FAKE_PASSWORD], text, serialized)


# --- /data/config redirect log (L2) -----------------------------------------


@PATCHER_STATES
def test_data_config_redirect_log_masks_external_source_url(capfd, scrub):
    """With the patcher on, it also masks this line's ``str`` extra, so only
    the patcher-off arm depends on the call site's ``redact_url``."""
    external_url = (
        f"https://{FAKE_USER}:{FAKE_PASSWORD}@config.example.com/sources"
        f"?api_key={FAKE_KEY}"
    )
    client = _client(ServerDataSourceConfig(external_source_url=external_url))

    with _captured_logs_with_patcher(scrub) as logs:
        response = client.get(
            opal_server_config.DATA_CONFIG_ROUTE,
            headers={"Authorization": f"Bearer {CLIENT_JWT}"},
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == set_url_query_param(
        external_url, "token", CLIENT_JWT
    )
    redirected = _single_record(logs, "Source configuration is available at")
    assert (
        redirected["extra"]["url"]
        == "https://***@config.example.com/sources?api_key=***"
    )
    _assert_absent(
        [FAKE_USER, FAKE_PASSWORD, FAKE_KEY, CLIENT_JWT], logs.text, logs.serialized
    )
    _assert_sinks_healthy(capfd, logs.sink_ids)


# --- default update-callback report log (L3) --------------------------------


@PATCHER_STATES
def test_default_callback_report_log_masks_entry_url_and_config(capfd, scrub):
    client = _client(ServerDataSourceConfig(config={"entries": []}))

    with _captured_logs_with_patcher(scrub) as logs:
        response = client.post(
            opal_server_config.DATA_CALLBACK_DEFAULT_ROUTE,
            json=_report_payload(REPORT_URL),
        )

    assert response.status_code == 200
    assert response.json() == {}
    report = _single_record(logs, "Received update report")["extra"]["report"]
    entry = report["reports"][0]["entry"]
    assert entry["url"] == REDACTED_REPORT_URL
    assert "config" not in entry and "data" not in entry
    assert report["update_id"] == "fake-update"
    assert report["policy_hash"] == "fake-policy-hash"
    assert report["user_data"] == {"tenant": "t-1"}
    _assert_absent(
        [FAKE_USER, FAKE_PASSWORD, FAKE_KEY, FAKE_HEADER, FAKE_DATA],
        logs.text,
        logs.serialized,
    )
    _assert_sinks_healthy(capfd, logs.sink_ids)


def test_scrub_patcher_masks_str_extras_only():
    """The patcher masks the message and ``str`` extras; a dict extra reaches a
    ``serialize=True`` sink as logged.

    So a URL inside a dict extra has to be redacted at the call site, as
    ``_report_for_log`` does. If the patcher starts masking nested
    values, the patcher-on arm above needs another carrier that only the
    call site can clean.
    """
    with _captured_logs_with_patcher(scrub=True) as logs:
        logger.info("probe {report}", report={"url": REPORT_URL}, url=REPORT_URL)

    (record,) = _records(logs.serialized, "probe")
    assert record["extra"]["report"] == {"url": REPORT_URL}
    assert record["extra"]["url"] == REDACTED_REPORT_URL
    assert FAKE_PASSWORD not in record["message"]


def test_patcher_off_arm_replaces_an_installed_scrub_patcher():
    """The patcher-off arm turns off a scrub patcher that is already global.

    In a full run, earlier test files leave ``configure_logs``'s patcher
    installed. If the off arm kept it, the off arm would mask ``str``
    extras too, and the redirect test would pass without the call site's
    ``redact_url``.
    """
    with _captured_logs_with_patcher(scrub=True):
        with _captured_logs_with_patcher(scrub=False) as logs:
            logger.info("probe", url=REPORT_URL)

    (record,) = _records(logs.serialized, "probe")
    assert record["extra"]["url"] == REPORT_URL


@PATCHER_STATES
def test_captured_logs_restores_the_previous_patcher(scrub):
    def previous_patcher(record) -> None:
        pass

    with without_log_patcher():
        logger.configure(patcher=previous_patcher)
        with _captured_logs_with_patcher(scrub):
            pass

        assert logger._core.patcher is previous_patcher


def test_sink_health_check_detects_a_failing_sink(capfd):
    def failing_sink(message: str) -> None:
        raise RuntimeError("sink failed")

    sink_id = logger.add(failing_sink, level="DEBUG")
    try:
        logger.info("probe")
    finally:
        logger.remove(sink_id)

    with pytest.raises(AssertionError):
        _assert_sinks_healthy(capfd, [sink_id])


# --- _report_for_log ---------------------------------------------------------


def test_report_for_log_redacts_every_entry():
    assert _rendered_urls(
        f"https://{FAKE_USER}:{FAKE_PASSWORD}@a.example.com/one?token={FAKE_KEY}",
        f"https://b.example.com/two?api_key={FAKE_KEY}&page=2",
        f"https://c.example.com/three#access_token={FAKE_KEY}",
    ) == [
        "https://***@a.example.com/one?token=***",
        "https://b.example.com/two?api_key=***&page=2",
        "https://c.example.com/three#access_token=***",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://data.example.com/v1?region=eu&page=2",
        "https://data.example.com/a%20b?q=%2F",
        "http://[bad",
        "",
    ],
    ids=["plain-params", "percent-encoded", "unparsable", "empty"],
)
def test_report_for_log_leaves_urls_without_auth_unchanged(url):
    assert _rendered_urls(url) == [url]


def test_report_for_log_empty_reports():
    report = DataUpdateReport(update_id="u", reports=[])

    assert data_api._report_for_log(report) == {
        "update_id": "u",
        "reports": [],
        "policy_hash": None,
        "user_data": {},
    }


def test_report_for_log_drops_config_and_data_keeps_the_rest():
    report = DataUpdateReport.model_validate(_report_payload(REPORT_URL))
    snapshot = report.model_copy(deep=True)

    rendered = data_api._report_for_log(report)

    (entry_report,) = rendered["reports"]
    assert set(entry_report["entry"]) == {"url", "topics", "dst_path", "save_method"}
    assert entry_report["fetched"] is True
    assert entry_report["saved"] is True
    assert entry_report["hash"] == "fake-entry-hash"
    assert rendered["update_id"] == "fake-update"
    assert rendered["policy_hash"] == "fake-policy-hash"
    assert rendered["user_data"] == {"tenant": "t-1"}
    assert report == snapshot


# --- policy watcher failure log (L8) ----------------------------------------


@pytest.mark.asyncio
async def test_policy_watcher_failure_log_masks_remote_auth(monkeypatch):
    monkeypatch.setattr(watcher_task_module.os, "kill", lambda pid, sig: None)
    watcher = watcher_task_module.BasePolicyWatcherTask(pubsub_endpoint=None)
    error = RuntimeError(
        f"fetch failed for https://fakeuser:{FAKE_PASSWORD}@git.example.com/org/policy.git"
    )

    with _captured_logs() as (text, serialized):
        await watcher._fail(error)

    failed = [line for line in serialized if "policy watcher failed" in line]
    assert failed and "git.example.com/org/policy.git" in failed[0], serialized
    _assert_absent([FAKE_PASSWORD], text, serialized)


# --- RPC library DEBUG logs (M1) --------------------------------------------


@pytest.fixture
def stdlib_logs_to_loguru():
    """Route stdlib logging into loguru the way configure_logs() does (root
    handler = InterceptHandler, root level 0), and restore everything after."""
    root = logging.getLogger()
    rpc_logger = logging.getLogger(server_module.RPC_LIBRARY_LOGGER_NAME)
    saved_root_level = root.level
    saved_rpc_level = rpc_logger.level
    handler = InterceptHandler()
    root.addHandler(handler)
    root.setLevel(logging.NOTSET)
    rpc_logger.setLevel(logging.NOTSET)
    try:
        yield
    finally:
        root.removeHandler(handler)
        root.setLevel(saved_root_level)
        rpc_logger.setLevel(saved_rpc_level)


def _emit_rpc_library_records():
    """One DEBUG record shaped like RpcChannel's request log (payload included)
    and one INFO lifecycle record, both from the libraries' own loggers."""
    channel_logger = get_rpc_library_logger("RPC_CHANNEL")
    pubsub_logger = get_rpc_library_logger("pubsub.EventNotifier")
    channel_logger.debug(
        "Handling RPC request - %s",
        {"request": {"headers": {"Authorization": FAKE_HEADER}}},
    )
    pubsub_logger.debug("notify %s", {"Authorization": FAKE_HEADER})
    channel_logger.info("Client connected")


def test_no_rpc_logs_drops_library_debug_records(monkeypatch, stdlib_logs_to_loguru):
    monkeypatch.setattr(opal_server_config, "NO_RPC_LOGS", True)
    server_module.configure_rpc_library_logs()

    with _captured_logs() as (text, serialized):
        _emit_rpc_library_records()

    assert any("Client connected" in line for line in text), text
    # Checked on the record text as well as the header value: the records must
    # be dropped, not just masked.
    assert not any("Handling RPC request" in line for line in text), text
    assert not any("notify" in line for line in text), text
    _assert_absent([FAKE_HEADER], text, serialized)


def test_rpc_library_debug_records_flow_when_no_rpc_logs_is_off(
    monkeypatch, stdlib_logs_to_loguru
):
    """The inverse, so the test above cannot pass because the records never
    reach loguru in the first place."""
    monkeypatch.setattr(opal_server_config, "NO_RPC_LOGS", False)
    server_module.configure_rpc_library_logs()

    with _captured_logs() as (text, _serialized):
        _emit_rpc_library_records()

    assert any("Handling RPC request" in line for line in text), text
    assert any("notify" in line for line in text), text
