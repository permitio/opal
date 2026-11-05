"""An error raised inside a FetchingEngine context is logged with its
traceback, without the request headers aiohttp's ``repr()`` would render."""

import json
import logging

import pytest
from opal_common.fetcher import FetchingEngine
from opal_common.logging_utils.intercept import InterceptHandler
from opal_common.tests.redaction_fixtures import capture_logs, response_error

FAKE_KEY = "FAKE-KEY-123"


@pytest.fixture
def fetcher_logs_to_loguru():
    """Route the fetcher's stdlib logger into loguru, as ``configure_logs``
    does in production."""
    fetcher_logger = logging.getLogger("opal.fetcher")
    handler = InterceptHandler()
    fetcher_logger.addHandler(handler)
    try:
        yield
    finally:
        fetcher_logger.removeHandler(handler)


@pytest.mark.asyncio
async def test_engine_context_error_log_omits_auth_header(fetcher_logs_to_loguru):
    error = response_error({"Authorization": f"Bearer {FAKE_KEY}"})
    with capture_logs() as logs:
        with pytest.raises(type(error)):
            async with FetchingEngine(worker_count=1):
                raise error

    # Other fetcher records (e.g. provider registration) may be captured too, and
    # if an earlier test ran configure_logs the root logger forwards a copy.
    errors = [
        record
        for record in (json.loads(line)["record"] for line in logs.serialized)
        if record["level"]["name"] == "ERROR"
    ]
    assert errors
    for record in errors:
        assert record["message"] == (
            "Error occurred within FetchingEngine context: ClientResponseError: "
            "502, message='Bad Gateway', url='http://example.com/v1/data'"
        )
        # the traceback is logged too
        assert record["exception"]["type"] == "ClientResponseError"
    assert "Traceback" in logs.combined
    assert FAKE_KEY not in logs.combined
