"""Log sites in opal-server's data router must redact auth.

Covers auth carried in a client's update report. The route tests check a
text sink and a ``serialize=True`` sink: loguru keeps a log call's keyword
arguments in ``record["extra"]``, which the JSON sink prints verbatim. The
sinks are not wrapped in ``CredentialScrubbingStream``, and each route test
runs with the patcher ``configure_logs`` installs both off (the sinks see
exactly what the call site emits) and on.
"""

import json
from contextlib import ExitStack, contextmanager
from typing import Any, Dict, Iterator, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger
from opal_common.logger import _scrub_record_message
from opal_common.schemas.data import DataUpdateReport, ServerDataSourceConfig
from opal_common.tests.log_capture import starting_with
from opal_common.tests.redaction_fixtures import CapturedLogs, without_log_patcher
from opal_server.config import opal_server_config
from opal_server.data import api as data_api

FAKE_USER = "fakeuser"
FAKE_PASSWORD = "fakepass-FAKE-456"
FAKE_KEY = "FAKE-KEY-123"
FAKE_HEADER = "Bearer FAKE-KEY-789"
FAKE_DATA = "FAKE-DATA-PAYLOAD"

REPORT_URL = (
    f"https://{FAKE_USER}:{FAKE_PASSWORD}@data.example.com/v1"
    f"?token={FAKE_KEY}&region=eu"
)
REDACTED_REPORT_URL = "https://***@data.example.com/v1?token=***&region=eu"

PATCHER_STATES = pytest.mark.parametrize(
    "scrub", [False, True], ids=["patcher-off", "patcher-on"]
)


class FakeAuthenticator:
    def __call__(self) -> Dict[str, Any]:
        return {}


@contextmanager
def _scrub_patcher() -> Iterator[None]:
    """Installs the patcher ``configure_logs`` installs, restoring the previous
    one on exit."""
    previous = logger._core.patcher
    logger.configure(patcher=_scrub_record_message)
    try:
        yield
    finally:
        # configure() ignores patcher=None, so restore the attribute itself
        logger._core.patcher = previous


@contextmanager
def _captured_logs(scrub: bool) -> Iterator[Tuple[CapturedLogs, List[int]]]:
    """Captures loguru output as a text sink and a ``serialize=True`` sink,
    with the production patcher on (``scrub``) or off.

    Yields the captured lines and the two sinks' handler ids.
    """
    logs = CapturedLogs()
    with ExitStack() as stack:
        stack.enter_context(_scrub_patcher() if scrub else without_log_patcher())
        text_id = logger.add(
            logs.text.append, level="DEBUG", colorize=False, diagnose=False
        )
        stack.callback(logger.remove, text_id)
        serialized_id = logger.add(
            logs.serialized.append, level="DEBUG", serialize=True
        )
        stack.callback(logger.remove, serialized_id)
        yield logs, [text_id, serialized_id]


def _records(serialized: List[str], prefix: str) -> List[Dict[str, Any]]:
    return starting_with([json.loads(line)["record"] for line in serialized], prefix)


def _lines(text: List[str], phrase: str) -> List[str]:
    return [line for line in text if phrase in line]


def _assert_sinks_healthy(
    capfd: pytest.CaptureFixture[str], sink_ids: List[int]
) -> None:
    """None of the given sinks failed (loguru prints the failure to stderr and
    drops the record).

    Keyed by handler id, since handlers other tests leave behind may
    report their own failures.
    """
    err = capfd.readouterr().err
    for sink_id in sink_ids:
        assert f"Logging error in Loguru Handler #{sink_id} ---" not in err, err


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
    report = DataUpdateReport.parse_obj(_report_payload(*urls))
    rendered = data_api._report_for_log(report)
    return [entry_report["entry"]["url"] for entry_report in rendered["reports"]]


# --- default update-callback report log --------------------------------------


@PATCHER_STATES
def test_default_callback_report_log_masks_entry_url_and_config(capfd, scrub):
    client = _client(ServerDataSourceConfig(config={"entries": []}))
    previous_patcher = logger._core.patcher

    with _captured_logs(scrub) as (logs, sink_ids):
        response = client.post(
            opal_server_config.DATA_CALLBACK_DEFAULT_ROUTE,
            json=_report_payload(REPORT_URL),
        )

    assert logger._core.patcher is previous_patcher
    assert response.status_code == 200
    assert response.json() == {}
    phrase = "Received update report"
    assert len(_lines(logs.text, phrase)) == 1, logs.text
    received = _records(logs.serialized, phrase)
    assert len(received) == 1, logs.serialized
    report = received[0]["extra"]["report"]
    entry = report["reports"][0]["entry"]
    assert entry["url"] == REDACTED_REPORT_URL
    assert "config" not in entry and "data" not in entry
    assert report["update_id"] == "fake-update"
    assert report["policy_hash"] == "fake-policy-hash"
    assert report["user_data"] == {"tenant": "t-1"}
    for value in [FAKE_USER, FAKE_PASSWORD, FAKE_KEY, FAKE_HEADER, FAKE_DATA]:
        assert value not in logs.combined, logs.combined
    _assert_sinks_healthy(capfd, sink_ids)


def test_scrub_patcher_masks_str_extras_only():
    """The patcher masks the message and ``str`` extras; a dict extra reaches a
    ``serialize=True`` sink as logged.

    So a URL inside a dict extra has to be redacted at the call site, as
    ``_report_for_log`` does. If the patcher starts masking nested
    values, the patcher-on arm above needs another carrier that only the
    call site can clean.
    """
    with _captured_logs(scrub=True) as (logs, _sink_ids):
        logger.info("probe {report}", report={"url": REPORT_URL}, url=REPORT_URL)

    (record,) = _records(logs.serialized, "probe")
    assert record["extra"]["report"] == {"url": REPORT_URL}
    assert record["extra"]["url"] == REDACTED_REPORT_URL
    assert FAKE_PASSWORD not in record["message"]


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
    report = DataUpdateReport.parse_obj(_report_payload(REPORT_URL))
    snapshot = report.copy(deep=True)

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
