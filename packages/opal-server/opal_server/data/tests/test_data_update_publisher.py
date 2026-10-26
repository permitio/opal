from opal_server.data.data_update_publisher import DataUpdatePublisher


def test_topic_combos():
    get_topic_combos = DataUpdatePublisher.get_topic_combos

    assert set(get_topic_combos("a/b/c")) == {"a", "a/b", "a/b/c"}
    assert set(get_topic_combos("x:a/b/c")) == {"x:a", "x:a/b", "x:a/b/c"}
    assert set(get_topic_combos("x:y:a/b/c")) == {"x:y:a", "x:y:a/b", "x:y:a/b/c"}
