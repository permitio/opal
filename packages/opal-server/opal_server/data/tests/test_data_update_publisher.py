import os

import pytest
from opal_common.schemas.data import DataSourceEntry, DataUpdate
from opal_common.tests.log_capture import capture_records, starting_with
from opal_server.data.data_update_publisher import DataUpdatePublisher


def test_topic_combos():
    get_topic_combos = DataUpdatePublisher.get_topic_combos

    assert set(get_topic_combos("a/b/c")) == {"a", "a/b", "a/b/c"}
    assert set(get_topic_combos("x:a/b/c")) == {"x:a", "x:a/b", "x:a/b/c"}
    assert set(get_topic_combos("x:y:a/b/c")) == {"x:y:a", "x:y:a/b", "x:y:a/b/c"}


class _RecordingPublisher:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append((topics, data))


@pytest.mark.asyncio
async def test_publish_data_updates_line_is_debug_and_missing_topics_warning_stays():
    """The per-update line is DEBUG (PER-16361: at INFO it was one indexed line
    per data update); the missing-topics warning stays visible at the deployed
    level.

    Both lines redact the entries' credentials.
    """
    update = DataUpdate(
        reason="test reason",
        entries=[
            DataSourceEntry(url="http://example.com/a", topics=["a/b"]),
            DataSourceEntry(
                url="https://user:s3cret@example.com/b?token=FAKE-TOKEN", topics=[]
            ),
        ],
    )

    with capture_records() as logs:
        await DataUpdatePublisher(_RecordingPublisher()).publish_data_updates(update)

    pid = os.getpid()
    [line] = starting_with(logs.emitted, f"[{pid}] Publishing data update to topics:")
    assert line["level"].name == "DEBUG"
    assert line["extra"]["topics"] == {"a", "a/b"}
    assert line["extra"]["reason"] == "test reason"
    # Logged entries keep the topics as given, from before the expansion.
    assert [e["topics"] for e in line["extra"]["entries"]] == [["a/b"], []]
    # Shown at DEBUG, the entries' URLs are redacted at the call site.
    logged_urls = [e["url"] for e in line["extra"]["entries"]]
    assert logged_urls[0] == "http://example.com/a"
    assert "example.com/b" in logged_urls[1]
    assert "s3cret" not in logged_urls[1]
    assert "FAKE-TOKEN" not in logged_urls[1]

    [warning] = starting_with(logs.emitted, f"[{pid}] No topics were provided")
    assert warning["level"].name == "WARNING"
    assert "s3cret" not in warning["message"]
    assert "FAKE-TOKEN" not in warning["message"]

    assert starting_with(logs.deployed, f"[{pid}] No topics were provided")
    assert not starting_with(logs.deployed, f"[{pid}] Publishing data update")
