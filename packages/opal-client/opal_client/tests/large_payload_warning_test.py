"""A warning is logged when the data fetched for an entry is very large, so a
policy store that dies of memory exhaustion can be traced to its cause."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from opal_client.config import opal_client_config
from opal_client.data.updater import DataUpdater
from opal_client.policy_store.mock_policy_store_client import MockPolicyStoreClient
from opal_common.schemas.data import DataSourceEntry
from opal_common.tests.redaction_fixtures import capture_logs

FAKE_KEY = "FAKE-KEY-123"
CREDENTIALED_URL = f"https://user:{FAKE_KEY}@data.example.com/users?token={FAKE_KEY}"
WARNING = "is large"


def make_updater(fetched) -> DataUpdater:
    fetcher = MagicMock()
    fetcher.handle_url = AsyncMock(return_value=fetched)
    return DataUpdater(
        token="fake-client-token",
        pubsub_url="ws://localhost:1/ws",
        data_sources_config_url="http://localhost:1/data/config",
        policy_store=MockPolicyStoreClient(),
        data_fetcher=fetcher,
        data_topics=["policy_data"],
        should_send_reports=False,
    )


def make_entry() -> DataSourceEntry:
    return DataSourceEntry(
        url=CREDENTIALED_URL, topics=["policy_data"], dst_path="/users"
    )


@pytest.fixture
def threshold(monkeypatch):
    def set_threshold(value: int):
        monkeypatch.setattr(
            opal_client_config, "DATA_UPDATER_LARGE_PAYLOAD_WARNING_BYTES", value
        )

    return set_threshold


@pytest.mark.asyncio
async def test_large_payload_logs_warning_and_still_returns_data(threshold):
    threshold(100)
    data = {"users": ["x" * 20 for _ in range(20)]}
    updater = make_updater(data)

    with capture_logs() as logs:
        result = await updater._fetch_data(make_entry())

    assert result == data
    assert WARNING in logs.combined
    assert "dst_path='/users'" in logs.combined
    assert "warning threshold: 100 bytes" in logs.combined
    # the credentialed source url is redacted like in the other data logs
    assert FAKE_KEY not in logs.combined


@pytest.mark.asyncio
async def test_small_payload_does_not_warn(threshold):
    threshold(10_000)
    updater = make_updater({"alice": {"role": "admin"}})

    with capture_logs() as logs:
        await updater._fetch_data(make_entry())

    assert WARNING not in logs.combined


@pytest.mark.asyncio
async def test_payload_at_threshold_does_not_warn(threshold):
    data = {"a": "b"}
    threshold(len('{"a": "b"}'))
    updater = make_updater(data)

    with capture_logs() as logs:
        await updater._fetch_data(make_entry())

    assert WARNING not in logs.combined


@pytest.mark.asyncio
async def test_zero_threshold_disables_the_check(threshold):
    threshold(0)
    updater = make_updater({"users": ["x" * 1000]})

    with capture_logs() as logs:
        await updater._fetch_data(make_entry())

    assert WARNING not in logs.combined


@pytest.mark.asyncio
async def test_string_payload_is_measured_in_bytes(threshold):
    threshold(10)
    updater = make_updater("é" * 8)  # 8 characters, 16 bytes in utf-8

    with capture_logs() as logs:
        await updater._fetch_data(make_entry())

    assert "16 bytes" in logs.combined


@pytest.mark.asyncio
async def test_non_ascii_json_payload_is_measured_in_utf8_bytes(threshold):
    threshold(10)
    updater = make_updater({"k": "é" * 8})  # {"k": "éééééééé"} is 25 bytes in utf-8

    with capture_logs() as logs:
        await updater._fetch_data(make_entry())

    assert "25 bytes" in logs.combined
