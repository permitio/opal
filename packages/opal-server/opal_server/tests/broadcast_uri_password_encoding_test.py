"""OPAL_BROADCAST_URI credentials must reach the backbone byte-for-byte.

A Postgres password containing percent signs (``s3cretPw%071lS``) made
every server<->server broadcast connection fail and the client websocket get
dropped right after opening. Both broadcaster clients, asyncpg and redis-py,
percent-decode the password in the URI, so a ``%xx`` sequence written raw is
decoded before it reaches the backbone -- ``%07`` became a control character
-- and authentication failed.

The escape syntax is the *contract* (a URI user info is percent-decoded),
so the code cannot un-break existing URIs; what it can do is tell an
operator at startup when the password decodes to something no password
holds, a control character, without warning about a correctly escaped one.
"""
from urllib.parse import quote

import pytest
from loguru import logger
from opal_server.publisher import password_decodes_to_control_characters
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
        ("postgres://opal@db:5432/opal", False),
        ("postgres://opal:plain@db:5432/opal", False),
        ("kafka://broker:9092/topic", False),
        # the password from the report, written raw: %07 decodes to BEL
        ("postgres://opal:s3cretPw%071lS@db:5432/opal", True),
        # the same password escaped: %2507 decodes to the literal %07
        ("postgres://opal:s3cretPw%25071lS@db:5432/opal", False),
        ("redis://:p%40ss@host:6379/0", False),
        ("redis://:p%25ss@host:6379/0", False),
        ("redis://:p%0Ass@host:6379/0", True),
        ("rediss://opal:p%7Fss@host:6380", True),
        # a % that starts no escape is kept as written
        ("redis://:100%@host:6379", False),
        ("postgres://opal:x@[::1/opal", False),
    ],
)
def test_password_decodes_to_control_characters(uri, expected):
    assert password_decodes_to_control_characters(uri) is expected


def test_escaped_password_round_trips_through_asyncpg_parsing():
    """``quote`` output must survive asyncpg's percent-decoding of the user
    info: what we quote is what Postgres receives."""
    from urllib.parse import unquote, urlsplit

    password = "s3cretPw%071lS"
    uri = f"postgres://opal:{quote(password)}@db:5432/opal"
    parts = urlsplit(uri)
    # asyncpg partitions the raw netloc itself, then unquotes each side
    auth, _, hostspec = parts.netloc.rpartition("@")
    _, _, raw_password = auth.partition(":")
    assert unquote(raw_password) == password
    assert hostspec == "db:5432"


def test_warning_logged_for_raw_percent_password(captured_warnings):
    """PubSub must surface the encoding pitfall at startup instead of letting
    the broadcaster fail invisibly."""
    uri = "postgres://opal:s3cretPw%071lS@db:5432/opal"
    pubsub = PubSub(signer=object(), broadcaster_uri=uri)
    warnings = [r for r in captured_warnings if r["level"].name == "WARNING"]
    assert warnings, "a raw % in the password must produce a startup warning"
    # the warning must not leak the credentials themselves
    assert all("s3cretPw" not in str(r["message"]) for r in warnings)
    # the warning must not change which broadcaster gets built
    assert isinstance(pubsub.broadcaster, ReconnectingBroadcaster)


@pytest.mark.parametrize(
    "uri",
    [
        "postgres://opal:plain@db:5432/opal",
        "postgres://opal:s3cretPw%25071lS@db:5432/opal",
    ],
    ids=["plain", "escaped"],
)
def test_no_warning_for_plain_or_escaped_password(captured_warnings, uri):
    PubSub(signer=object(), broadcaster_uri=uri)
    assert not [r for r in captured_warnings if r["level"].name == "WARNING"]


def test_warning_logged_for_raw_percent_redis_password(captured_warnings):
    PubSub(signer=object(), broadcaster_uri="redis://:s3cretPw%071lS@redis:6379")
    warnings = [r for r in captured_warnings if r["level"].name == "WARNING"]
    assert len(warnings) == 1
    assert "%25" in str(warnings[0]["message"])
    assert "s3cretPw" not in str(warnings[0]["message"])
