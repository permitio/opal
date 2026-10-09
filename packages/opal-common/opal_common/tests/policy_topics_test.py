from pathlib import Path

from opal_common.topics.utils import (
    policy_topics,
    pubsub_topics_from_directories,
    pubsub_topics_from_sources,
)


def test_policy_topics_include_source_id_only_when_configured():
    directories = [Path("policy")]

    assert policy_topics(directories) == ["policy:policy"]
    assert policy_topics(directories, source_id="team-a") == [
        "policy:team-a:policy"
    ]


def test_client_topic_builder_uses_source_namespaces():
    assert pubsub_topics_from_directories(["policy"], source_id="team-a") == [
        "policy:team-a:policy"
    ]


def test_client_topic_builder_accepts_multiple_sources():
    assert pubsub_topics_from_sources(["policy"], ["team-a", "team-b"]) == [
        "policy:team-a:policy",
        "policy:team-b:policy",
    ]