import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from loguru import logger
from pydantic import BaseModel

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
)
sys.path.append(root_dir)

from opal_client.callbacks.register import CallbacksRegister
from opal_client.callbacks.reporter import CallbacksReporter, build_callback_payload
from opal_client.config import opal_client_config
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.schemas.data import (
    DataEntryReport,
    DataSourceEntry,
    DataSourceEntryWithPollingInterval,
    DataUpdateReport,
)
from opal_common.tests.redaction_fixtures import capture_logs, response_error

CALLBACK_URL = "http://callback.example.com/report"
EXTRA_CALLBACK_URL = "http://extra-callback.example.com/report"
SECRET_TOKEN = "Bearer super-secret-token-must-not-leak"


@pytest.fixture
def capture_loguru():
    """Capture loguru output with serialize=True.

    OPAL's production log sinks can be configured with LOG_SERIALIZE=true, which
    dumps the full record (including ``record["extra"]``) as JSON. That is the
    scenario in which #901 leaked credentials, so the regression sink must
    serialize too — otherwise the default format string hides ``extra`` fields
    and the test passes vacuously.
    """
    captured: list[str] = []
    sink_id = logger.add(
        lambda message: captured.append(str(message)),
        level="DEBUG",
        serialize=True,
    )
    try:
        yield captured
    finally:
        logger.remove(sink_id)


@pytest.mark.asyncio
async def test_report_update_results_does_not_log_fetcher_config(capture_loguru):
    """Regression test for #901: the reporter must not log FetcherConfig.

    HttpFetcherConfig may carry Authorization headers and the full report
    payload (assigned to ``config.data`` just before the log line).
    Only the URLs are safe to log.
    """
    register = CallbacksRegister()
    register.put(
        CALLBACK_URL,
        config=HttpFetcherConfig(headers={"Authorization": SECRET_TOKEN}),
    )

    fetcher = MagicMock()
    fetcher.handle_urls = AsyncMock(return_value=[])

    reporter = CallbacksReporter(register=register, data_fetcher=fetcher)
    report = DataUpdateReport(update_id="test-update", reports=[])

    extra_config = HttpFetcherConfig(headers={"Authorization": SECRET_TOKEN})
    await reporter.report_update_results(
        report=report,
        extra_callbacks=[(EXTRA_CALLBACK_URL, extra_config)],
    )

    combined_log = "\n".join(capture_loguru)
    # the secret token itself must never appear in any log line
    assert SECRET_TOKEN not in combined_log
    # the HttpFetcherConfig repr (which embeds headers and data) must never appear
    assert "HttpFetcherConfig" not in combined_log
    assert "headers=" not in combined_log
    # the URLs themselves are expected in the log line
    assert CALLBACK_URL in combined_log
    assert EXTRA_CALLBACK_URL in combined_log

    # the fetcher must still receive the full (url, config, None) tuple shape
    fetcher.handle_urls.assert_awaited_once()
    forwarded_requests = fetcher.handle_urls.await_args.args[0]
    assert len(forwarded_requests) == 2
    forwarded_urls = [request[0] for request in forwarded_requests]
    assert CALLBACK_URL in forwarded_urls
    assert EXTRA_CALLBACK_URL in forwarded_urls
    for _, config, sentinel in forwarded_requests:
        assert isinstance(config, HttpFetcherConfig)
        assert config.headers == {"Authorization": SECRET_TOKEN}
        assert sentinel is None


FAKE_KEY = "FAKE-KEY-123"
CREDENTIALED_URL = f"https://user:{FAKE_KEY}@data.example.com/x?token={FAKE_KEY}"


def _report() -> DataUpdateReport:
    return DataUpdateReport(
        update_id="update-1",
        policy_hash="policy-hash",
        user_data={"client": "c1"},
        reports=[
            DataEntryReport(
                entry=DataSourceEntry(
                    url=CREDENTIALED_URL,
                    config={"headers": {"Authorization": f"Bearer {FAKE_KEY}"}},
                    data={"inline": FAKE_KEY},
                    topics=["policy_data"],
                    dst_path="/users",
                ),
                fetched=True,
                saved=True,
                hash="data-hash",
            ),
            DataEntryReport(
                entry=DataSourceEntryWithPollingInterval(
                    url="http://data.example.com/y",
                    config={"headers": {"Authorization": f"Bearer {FAKE_KEY}"}},
                    periodic_update_interval=30,
                ),
                fetched=False,
            ),
        ],
    )


def _recording_fetcher(results=None) -> MagicMock:
    fetcher = MagicMock()
    fetcher.handle_urls = AsyncMock(return_value=results or [])
    return fetcher


def _sent_payloads(fetcher: MagicMock) -> list:
    return [config.data for _, config, _ in fetcher.handle_urls.await_args.args[0]]


@pytest.mark.asyncio
async def test_callback_payload_omits_entry_config_and_data():
    register = CallbacksRegister()
    register.put(CALLBACK_URL, config=HttpFetcherConfig())
    fetcher = _recording_fetcher()

    await CallbacksReporter(register, data_fetcher=fetcher).report_update_results(
        _report()
    )

    (payload,) = _sent_payloads(fetcher)
    assert FAKE_KEY not in payload
    sent = json.loads(payload)
    assert sent["update_id"] == "update-1"
    assert sent["policy_hash"] == "policy-hash"
    assert sent["user_data"] == {"client": "c1"}
    first, second = sent["reports"]
    assert {
        "fetched": True,
        "saved": True,
        "hash": "data-hash",
    }.items() <= first.items()
    assert first["entry"] == {
        "url": "https://***@data.example.com/x?token=***",
        "topics": ["policy_data"],
        "dst_path": "/users",
        "save_method": "PUT",
    }
    # subclass-only entry fields are still sent
    assert second["entry"]["periodic_update_interval"] == 30
    assert "config" not in second["entry"] and "data" not in second["entry"]


@pytest.mark.asyncio
async def test_callback_payload_parses_on_the_receiving_side():
    """opal-server parses the payload as a DataUpdateReport; other receivers may
    declare ``config: dict = {}``, which rejects null - so the keys are omitted."""

    class _Receiver(BaseModel):
        url: str
        config: dict = {}

    register = CallbacksRegister()
    register.put(CALLBACK_URL, config=HttpFetcherConfig())
    fetcher = _recording_fetcher()

    await CallbacksReporter(register, data_fetcher=fetcher).report_update_results(
        _report()
    )

    (payload,) = _sent_payloads(fetcher)
    parsed = DataUpdateReport.parse_raw(payload)
    assert parsed.reports[0].entry.config is None
    assert parsed.reports[0].saved is True
    for entry_report in json.loads(payload)["reports"]:
        _Receiver.parse_obj(entry_report["entry"])


@pytest.mark.asyncio
async def test_reporting_leaves_registered_configs_unchanged(monkeypatch):
    """GET /callbacks serves the registered configs, and
    DEFAULT_UPDATE_CALLBACK_CONFIG backs every url-only callback - neither may
    pick up the report."""
    default_config = HttpFetcherConfig(method="post")
    monkeypatch.setattr(
        opal_client_config, "DEFAULT_UPDATE_CALLBACK_CONFIG", default_config
    )
    register = CallbacksRegister(initial_callbacks=[EXTRA_CALLBACK_URL])
    key = register.put(
        CALLBACK_URL, config=HttpFetcherConfig(headers={"Authorization": "x"})
    )
    one_time_config = HttpFetcherConfig()
    fetcher = _recording_fetcher()

    await CallbacksReporter(register, data_fetcher=fetcher).report_update_results(
        _report(), extra_callbacks=[("http://one-time.example.com", one_time_config)]
    )

    payloads = _sent_payloads(fetcher)
    assert len(payloads) == 3 and all(payloads)
    assert register.get(key).config.data is None
    assert all(entry.config.data is None for entry in register.all())
    assert default_config.data is None
    assert one_time_config.data is None


@pytest.mark.asyncio
async def test_failed_callback_log_omits_auth_header():
    register = CallbacksRegister()
    register.put(CALLBACK_URL, config=HttpFetcherConfig())
    error = response_error({"Authorization": f"Bearer {FAKE_KEY}"})
    fetcher = _recording_fetcher(results=[(CALLBACK_URL, HttpFetcherConfig(), error)])

    with capture_logs() as logs:
        await CallbacksReporter(register, data_fetcher=fetcher).report_update_results(
            DataUpdateReport(reports=[])
        )

    assert f"Failed to send report to {CALLBACK_URL}" in logs.combined
    assert "info=ClientResponseError: 502" in logs.combined
    assert FAKE_KEY not in logs.combined


@pytest.mark.asyncio
async def test_report_failure_message_omits_exception_text():
    register = CallbacksRegister()
    register.put(CALLBACK_URL, config=HttpFetcherConfig())
    fetcher = MagicMock()
    fetcher.handle_urls = AsyncMock(side_effect=RuntimeError(CREDENTIALED_URL))

    with capture_logs() as logs:
        await CallbacksReporter(register, data_fetcher=fetcher).report_update_results(
            DataUpdateReport(reports=[])
        )

    record = json.loads(logs.serialized[-1])["record"]
    # the exception is recorded as the record's exception, not in its message
    assert record["message"] == "Failed to execute report_update_results"
    assert record["exception"]["type"] == "RuntimeError"


def test_payload_without_entries_matches_report_json():
    """Policy updates report no entries; their payload is byte-for-byte what
    was sent before the entry fields were trimmed."""
    report = DataUpdateReport(
        policy_hash="policy-hash", reports=[], user_data={"name": "Zoë", "ratio": 0.5}
    )

    assert build_callback_payload(report) == report.json()


async def _html_error(request: web.Request) -> web.Response:
    return web.Response(
        status=500, text="<html>internal error</html>", content_type="text/html"
    )


async def _json_error(request: web.Request) -> web.Response:
    return web.json_response({"error": "callback failed"}, status=500)


@pytest.mark.asyncio
async def test_every_callback_error_response_is_logged():
    """A non-JSON error body from one callback must not stop the rest from
    being logged."""
    app = web.Application()
    app.router.add_post("/html", _html_error)
    app.router.add_post("/json", _json_error)
    register = CallbacksRegister()
    register.put(CALLBACK_URL, config=HttpFetcherConfig())

    async with TestServer(app) as server, aiohttp.ClientSession() as session:
        responses = []
        for path in ("/html", "/json"):
            response = await session.post(server.make_url(path))
            await response.read()
            responses.append(
                (str(server.make_url(path)), HttpFetcherConfig(), response)
            )
        fetcher = _recording_fetcher(results=responses)

        with capture_logs() as logs:
            await CallbacksReporter(
                register, data_fetcher=fetcher
            ).report_update_results(DataUpdateReport(reports=[]))

    assert (
        "got response code 500 with error: <html>internal error</html>" in logs.combined
    )
    assert (
        "got response code 500 with error: {'error': 'callback failed'}"
        in logs.combined
    )
    assert "Failed to execute report_update_results" not in logs.combined
