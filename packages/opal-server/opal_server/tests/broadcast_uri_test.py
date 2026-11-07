from urllib.parse import unquote, urlsplit

from opal_server.broadcast_uri import normalize_broadcaster_uri


def test_normalize_broadcaster_uri_preserves_none_and_host_only():
    assert normalize_broadcaster_uri(None) is None
    assert (
        normalize_broadcaster_uri("postgres://localhost:5432/postgres")
        == "postgres://localhost:5432/postgres"
    )


def test_normalize_broadcaster_uri_encodes_percent_sequence_in_password():
    raw_password = "bnvcGy1pU%071lS"
    raw_uri = f"postgres://postgres:{raw_password}@localhost:5432/postgres"
    normalized = normalize_broadcaster_uri(raw_uri)
    parsed = urlsplit(normalized)
    assert parsed.hostname == "localhost"
    assert parsed.port == 5432
    assert unquote(parsed.password) == raw_password


def test_normalize_broadcaster_uri_encodes_uri_delimiters_in_password():
    raw_password = "p@ss:w/rd?a=1#frag%20"
    raw_uri = f"postgresql://opal_user:{raw_password}@db.internal:5432/opal_db"
    normalized = normalize_broadcaster_uri(raw_uri)
    parsed = urlsplit(normalized)
    assert parsed.username == "opal_user"
    assert parsed.hostname == "db.internal"
    assert parsed.port == 5432
    assert parsed.path == "/opal_db"
    assert unquote(parsed.password) == raw_password
