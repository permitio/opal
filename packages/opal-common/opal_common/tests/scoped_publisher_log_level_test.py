import pytest
from loguru import logger
from opal_common.tests.log_capture import capture_records, starting_with
from opal_common.topics.publisher import ScopedServerSideTopicPublisher


class _RecordingEndpoint:
    def __init__(self):
        self.published = []

    async def publish(self, topics, data=None):
        self.published.append((topics, data))


@pytest.mark.asyncio
async def test_scoped_publish_line_is_debug_and_still_publishes():
    """'Publishing to topics' is DEBUG (PER-16361).

    For a policy push it repeated the push's one INFO line ("Triggering
    policy update for scope").
    """
    endpoint = _RecordingEndpoint()

    with capture_records() as logs:
        logger.info("deployed-level control")
        async with ScopedServerSideTopicPublisher(endpoint, "s1") as publisher:
            await publisher.publish(["a", "b"], {"x": 1})

    assert endpoint.published == [(["s1:a", "s1:b"], {"x": 1})]
    [line] = starting_with(logs.emitted, "Publishing to topics:")
    assert line["message"] == "Publishing to topics: ['s1:a', 's1:b']"
    assert line["level"].name == "DEBUG"
    assert starting_with(logs.deployed, "deployed-level control")
    assert not starting_with(logs.deployed, "Publishing to topics:")
