"""opal_common.topics.listener: TopicCallback is a typing.Protocol, and
TopicListener drives the pub/sub client it is given."""

import typing

import pytest
from opal_common.topics.listener import TopicCallback, TopicListener


class _Client:
    """A PubSubClient stand-in that records what the listener asks of it."""

    def __init__(self) -> None:
        self.calls: list = []

    def subscribe(self, topic, callback) -> None:
        self.calls.append(("subscribe", topic, callback))

    def start_client(self, server_uri) -> None:
        self.calls.append(("start_client", server_uri))

    async def disconnect(self) -> None:
        self.calls.append(("disconnect",))

    async def wait_until_done(self) -> str:
        self.calls.append(("wait_until_done",))
        return "done"


class _Callback:
    """A TopicCallback: an awaitable result for a topic and its data."""

    def __init__(self) -> None:
        self.received: list = []

    async def __call__(self, topic, data) -> None:
        self.received.append((topic, data))


def test_topic_callback_is_a_typing_protocol():
    assert typing.Protocol in TopicCallback.__mro__
    with pytest.raises(TypeError):
        TopicCallback()


@pytest.mark.asyncio
async def test_the_listener_subscribes_each_topic_with_its_callback_then_starts():
    client = _Client()
    callback = _Callback()
    listener = TopicListener(
        client, "ws://server/ws", topics=["policy", "data"], callback=callback
    )

    async with listener:
        assert client.calls == [
            ("subscribe", "policy", callback),
            ("subscribe", "data", callback),
            ("start_client", "ws://server/ws"),
        ]
        assert await listener.wait_until_done() == "done"
        _, topic, subscribed = client.calls[0]
        await subscribed(topic, {"x": 1})

    assert client.calls[-2:] == [("wait_until_done",), ("disconnect",)]
    assert callback.received == [("policy", {"x": 1})]
