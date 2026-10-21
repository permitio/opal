"""Capture loguru records both as emitted and as a deployed sink receives them,
for tests that pin the level of a log line."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, List

from loguru import logger
from opal_common.tests.redaction_fixtures import without_log_patcher


@dataclass
class CapturedRecords:
    #: Every record at DEBUG and above.
    emitted: List[dict] = field(default_factory=list)
    #: What a sink at OPAL's default level (``LOG_LEVEL=INFO``) receives.
    deployed: List[dict] = field(default_factory=list)


def starting_with(records: List[dict], prefix: str) -> List[dict]:
    return [r for r in records if r["message"].startswith(prefix)]


@contextmanager
def capture_records() -> Iterator[CapturedRecords]:
    """Adds a DEBUG sink and an INFO sink for the duration of the block.

    The INFO sink is a real loguru sink, so a record missing from
    ``deployed`` is one loguru itself would not hand to a sink at the
    deployed level. The global patcher is disabled (see
    ``without_log_patcher``) so messages are what the call site emits.
    """
    captured = CapturedRecords()
    with without_log_patcher():
        sink_ids = [
            logger.add(lambda m: captured.emitted.append(m.record), level="DEBUG"),
            logger.add(lambda m: captured.deployed.append(m.record), level="INFO"),
        ]
        try:
            yield captured
        finally:
            for sink_id in sink_ids:
                logger.remove(sink_id)
