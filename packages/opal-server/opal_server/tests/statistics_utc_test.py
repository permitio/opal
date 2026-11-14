"""The server statistics' clock: another worker's keepalive keeps it in this
worker's server list until the keepalive timeout passes, and the uptime reports
when this worker started, in naive UTC as it always has.

Each test runs with the process's local time five hours east, then west, of
UTC (``local_time_off_utc``): a keepalive stamped by the local clock and
checked against the UTC clock is then five hours off, one way or the other.
"""

import asyncio
from datetime import datetime, timezone

import pytest
from opal_server.config import opal_server_config
from opal_server.statistics import OpalStatistics


@pytest.mark.asyncio
async def test_a_worker_just_heard_from_stays_listed(local_time_off_utc):
    stats = OpalStatistics(endpoint=None)

    await stats._receive_other_worker_keepalive_message(None, {"worker_id": "other"})
    await stats._expire_old_servers()

    assert "other" in stats.state.servers


@pytest.mark.asyncio
async def test_a_worker_not_heard_from_within_the_timeout_is_dropped(
    local_time_off_utc, monkeypatch
):
    monkeypatch.setattr(
        opal_server_config, "STATISTICS_SERVER_KEEPALIVE_TIMEOUT", "0.05"
    )
    stats = OpalStatistics(endpoint=None)

    await stats._receive_other_worker_keepalive_message(None, {"worker_id": "other"})
    await asyncio.sleep(0.1)
    await stats._expire_old_servers()

    assert stats.state.servers == {stats._worker_id}


def test_the_uptime_is_naive_utc_from_the_start(local_time_off_utc):
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    stats = OpalStatistics(endpoint=None)
    after = datetime.now(timezone.utc).replace(tzinfo=None)

    assert stats.state.uptime.tzinfo is None
    assert before <= stats.state.uptime <= after
    assert stats.state_brief.uptime == stats.state.uptime
