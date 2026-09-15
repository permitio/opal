import json

import pytest
from opal_common.fetcher.providers.http_fetch_provider import (
    HttpFetcherConfig,
    HttpMethods,
)
from opal_common.schemas.data import DataSourceEntry, DataUpdate
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
async def test_published_payload_is_json_serializable():
    """The published payload must contain only plain JSON types.

    A python-mode ``model_dump()`` keeps enum members (``HttpMethods.GET``
    inside a fetcher config), which v1's ``.dict()`` unwrapped at dump time but
    v2 does not - leaving a payload any downstream ``json.dumps`` rejects.
    """
    publisher = _RecordingPublisher()
    update = DataUpdate(
        reason="test",
        entries=[
            DataSourceEntry(
                url="http://example.com/data",
                topics=["policy_data"],
                config=HttpFetcherConfig(
                    headers={"Authorization": "Bearer x"}, method=HttpMethods.POST
                ),
            )
        ],
    )

    await DataUpdatePublisher(publisher).publish_data_updates(update)

    assert publisher.published, "nothing was published"
    for _topics, payload in publisher.published:
        # raises TypeError on an enum member surviving the dump
        json.dumps(payload)
