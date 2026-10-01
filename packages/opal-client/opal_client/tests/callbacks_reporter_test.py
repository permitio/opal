import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from loguru import logger

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
)
sys.path.append(root_dir)

from opal_client.callbacks.register import CallbacksRegister
from opal_client.callbacks.reporter import CallbacksReporter
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.schemas.data import DataUpdateReport

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
