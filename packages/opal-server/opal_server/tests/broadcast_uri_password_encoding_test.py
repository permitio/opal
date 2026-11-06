from urllib.parse import quote, unquote, urlsplit

import pytest
from loguru import logger
from opal_server.publisher import uri_has_percent_escapes
from opal_server.pubsub import PubSub
from opal_server.pubsub_resilience import ReconnectingBroadcaster


@pytest.fixture
def captured_warnings():
    records = []
    sink_id = logger.add(lambda m: records.append(m.record), level="DEBUG")
    yield records
    logger.remove(sink_id)


@pytest.mark.parametrize(
    "uri, expected",
    [
        ("postgres://db:5432/opal", False),
        ("postgres://opal:plain@db:5432/opal", False),
        ("kafka://broker:9092/topic", False),
        ("postgres://opal:bnvcGy1pU%071lS@db:5432/opal", True),
        ("postgres://opal:bnvcGy1pU%25071lS@db:5432/opal", True),
        ("redis://:p%40ss@host:6379/0", True),
    ],
)
def test_uri_has_percent_escapes(uri, expected):
    assert uri_has_percent_escapes(uri) is expected


def test_escaped_password_round_trips_through_asyncpg_parsing():
    password = "bnvcGy1pU%071lS"
    uri = f"postgres://opal:{quote(password)}@db:5432/opal"
    parts = urlsplit(uri)
    auth, _, hostspec = parts.netloc.rpartition("@")
    _, _, raw_password = auth.partition(":")
    assert unquote(raw_password) == password
    assert hostspec == "db:5432"


def test_warning_logged_for_raw_percent_password(captured_warnings):
    uri = "postgres://opal:bnvcGy1pU%071lS@db:5432/opal"
    pubsub = PubSub(signer=object(), broadcaster_uri=uri)
    warnings = [r for r in captured_warnings if r["level"].name == "WARNING"]
    assert warnings, "a % in the password must produce a startup warning"
    assert all("bnvcGy1pU" not in str(r["message"]) for r in warnings)
    assert isinstance(pubsub.broadcaster, ReconnectingBroadcaster)


def test_no_warning_for_plain_uri(captured_warnings):
    PubSub(signer=object(), broadcaster_uri="postgres://opal:plain@db:5432/opal")
    assert not [r for r in captured_warnings if r["level"].name == "WARNING"]
