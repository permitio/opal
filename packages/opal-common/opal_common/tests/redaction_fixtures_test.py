"""capture_logs records what a call site emits even after ``configure_logs``
has installed its masking patcher."""

import pytest
from loguru import logger
from opal_common.logger import _scrub_record_message
from opal_common.tests.redaction_fixtures import capture_logs

FAKE_KEY = "FAKE-KEY-123"


@pytest.fixture
def restore_patcher():
    previous = logger._core.patcher
    try:
        yield
    finally:
        logger._core.patcher = previous


@pytest.mark.parametrize("installed", [_scrub_record_message, None])
def test_capture_logs_bypasses_and_restores_the_global_patcher(
    restore_patcher, installed
):
    logger._core.patcher = installed

    with capture_logs() as logs:
        logger.info("sent {header}", header=f"Bearer {FAKE_KEY}")

    # the call site's own output, which the installed patcher would have masked
    assert FAKE_KEY in "\n".join(logs.text)
    assert FAKE_KEY in "\n".join(logs.serialized)
    assert logger._core.patcher is installed
