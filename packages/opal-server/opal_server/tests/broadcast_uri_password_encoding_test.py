"""OPAL_BROADCAST_URI credentials must reach the backbone byte-for-byte.

Issue #584: a Postgres password containing percent signs
(``bnvcGy1pU%071lS``) made every server<->server broadcast connection fail
and the client websocket get dropped right after opening. asyncpg
percent-decodes the user info of a DSN (asyncpg#472), so a ``%xx`` sequence
written raw into the URI is decoded before it reaches Postgres --
``%07`` became a control character -- and authentication failed.

The escape syntax is the *contract* (a URI user info is percent-decoded),
so the code cannot un-break existing URIs; what it can do is tell an
operator immediately, at startup, which side of the contract their URI is
on, instead of leaving the only visible symptom the cryptic client-side
"Client connection failed" / "connection closed" pair from the issue.
"""
from urllib.parse import quote

import pytest
from loguru import logger
from opal_server.publisher import uri_has_percent_escapes
from opal_server.pubsub import PubSub
from opal_server.pubsub_resilience import ReconnectingBroadcaster


@pytest.fixture
def captured_warnings():
    """Capture loguru records: OPAL scrubs URL credentials out of every log
    message (redact_url_in_text), so URI arguments must not be asserted on
    verbatim from the record text."""
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
        # the exact password from the issue, raw
        ("postgres://opal:bnvcGy1pU%071lS@db:5432/opal", True),
        # already escaped: %07 escaped as %2507 (flagged too: from the URI
        # alone the two readings are indistinguishable)
        ("postgres://opal:bnvcGy1pU%25071lS@db:5432/opal", True),
        ("redis://:p%40ss@host:6379/0", True),
    ],
)
def test_uri_has_percent_escapes(uri, expected):
    assert uri_has_percent_escapes(uri) is expected


def test_escaped_password_round_trips_through_asyncpg_parsing():
    """``quote`` output must survive asyncpg's percent-decoding of the user
    info: what we quote is what Postgres receives."""
    from urllib.parse import unquote, urlsplit

    password = "bnvcGy1pU%071lS"
    uri = f"postgres://opal:{quote(password)}@db:5432/opal"
    parts = urlsplit(uri)
    # asyncpg partitions the raw netloc itself, then unquotes each side
    auth, _, hostspec = parts.netloc.rpartition("@")
    _, _, raw_password = auth.partition(":")
    assert unquote(raw_password) == password
    assert hostspec == "db:5432"


def test_warning_logged_for_raw_percent_password(captured_warnings):
    """PubSub must surface the encoding pitfall at startup instead of letting
    the broadcaster fail invisibly (issue #584's diagnosis)."""
    uri = "postgres://opal:bnvcGy1pU%071lS@db:5432/opal"
    pubsub = PubSub(signer=object(), broadcaster_uri=uri)
    warnings = [r for r in captured_warnings if r["level"].name == "WARNING"]
    assert warnings, "a raw % in the password must produce a startup warning"
    # the warning must not leak the credentials themselves
    assert all("bnvcGy1pU" not in str(r["message"]) for r in warnings)
    # the warning must not change which broadcaster gets built
    assert isinstance(pubsub.broadcaster, ReconnectingBroadcaster)


def test_no_warning_for_plain_uri(captured_warnings):
    PubSub(signer=object(), broadcaster_uri="postgres://opal:plain@db:5432/opal")
    assert not [r for r in captured_warnings if r["level"].name == "WARNING"]
