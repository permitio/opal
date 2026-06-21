"""Regression tests for credential redaction in repr/str of credential-bearing
models (follow-up to #901 / #902).

OPAL logs via loguru. Credentials leaked because log statements interpolated
whole models (e.g. ``logger.info("... {entry}", entry=entry)``) or relied on
loguru's ``serialize=True`` sink, which dumps ``record["extra"]`` as JSON and
falls back to ``str()`` for non-JSON objects. ``RedactedReprMixin`` masks the
secret-bearing fields at the model layer so every current and future log site is
protected at once - while leaving ``.dict()`` / ``.json()`` (the wire format)
untouched.
"""

import pytest
from loguru import logger
from opal_common.fetcher.events import FetchEvent
from opal_common.fetcher.providers.fastapi_rpc_fetch_provider import (
    FastApiRpcFetchConfig,
)
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.http_utils import redact_url, redact_url_in_text
from opal_common.schemas.data import DataSourceEntry, DataUpdate

SECRET_TOKEN = "Bearer super-secret-token-must-not-leak"


def _models():
    """One instance of each credential-bearing model, all carrying SECRET_TOKEN."""
    return {
        "HttpFetcherConfig": HttpFetcherConfig(
            headers={"Authorization": SECRET_TOKEN}, data={"payload": SECRET_TOKEN}
        ),
        "DataSourceEntry": DataSourceEntry(
            url="http://data.example.com",
            save_method="PUT",
            config={"headers": {"Authorization": SECRET_TOKEN}},
            data={"payload": SECRET_TOKEN},
        ),
        "FetchEvent": FetchEvent(
            fetcher="HttpFetchProvider",
            url="http://data.example.com",
            config={"headers": {"Authorization": SECRET_TOKEN}},
        ),
        # rpc_arguments is a secret-bearing field on a different FetcherConfig
        # subclass; it must be redacted too (regression for a missed subclass).
        "FastApiRpcFetchConfig": FastApiRpcFetchConfig(
            rpc_method_name="publish",
            rpc_arguments={"token": SECRET_TOKEN},
        ),
    }


@pytest.mark.parametrize("name,model", list(_models().items()))
def test_repr_and_str_redact_secrets(name, model):
    """repr() / str() (used by f-strings and ``"{}".format``) must never expose
    the secret, and must show it was redacted."""
    assert SECRET_TOKEN not in repr(model), f"secret leaked in repr({name})"
    assert SECRET_TOKEN not in str(model), f"secret leaked in str({name})"
    assert SECRET_TOKEN not in f"{model}", f"secret leaked in f-string of {name}"
    assert "<redacted>" in repr(model), f"{name} did not redact anything"


def test_wire_serialization_is_not_redacted():
    """Redaction is only for human/log rendering - ``.dict()`` (the transport
    format) must still carry the real values so fetching keeps working."""
    cfg = HttpFetcherConfig(headers={"Authorization": SECRET_TOKEN})
    entry = DataSourceEntry(
        url="http://data.example.com",
        save_method="PUT",
        config={"headers": {"Authorization": SECRET_TOKEN}},
    )
    assert cfg.dict()["headers"]["Authorization"] == SECRET_TOKEN
    assert entry.dict()["config"]["headers"]["Authorization"] == SECRET_TOKEN


def test_nested_container_models_redact_transitively():
    """The objects actually published on the wire are containers like
    ``DataUpdate`` that hold ``DataSourceEntry`` objects. They carry no mixin
    themselves but must still redact via nested repr."""
    update = DataUpdate(
        reason="test",
        entries=[
            DataSourceEntry(
                url="http://data.example.com",
                save_method="PUT",
                config={"headers": {"Authorization": SECRET_TOKEN}},
                data={"payload": SECRET_TOKEN},
            )
        ],
    )
    assert SECRET_TOKEN not in repr(update)
    assert SECRET_TOKEN not in str(update)
    assert SECRET_TOKEN not in f"{update}"
    # wire format still carries the real value
    assert update.dict()["entries"][0]["config"]["headers"]["Authorization"] == (
        SECRET_TOKEN
    )


def test_loguru_serialize_does_not_leak():
    """The actual #901 scenario: a sink with ``serialize=True`` dumps the full
    record (including ``extra``) as JSON. Interpolating or binding any of these
    models must not put the secret on the wire."""
    captured: list[str] = []
    sink_id = logger.add(
        lambda message: captured.append(str(message)),
        level="DEBUG",
        serialize=True,
    )
    try:
        for model in _models().values():
            logger.info("logging model {model}", model=model)
            logger.bind(bound=model).info("bound model")
    finally:
        logger.remove(sink_id)

    combined = "\n".join(captured)
    assert SECRET_TOKEN not in combined, "secret leaked through loguru serialize=True"


def test_loguru_diagnose_does_not_leak_model_value():
    """With ``diagnose=True`` loguru renders local variable *values* in
    tracebacks (the #901-class vector). The model's own value must render
    redacted."""
    captured: list[str] = []
    sink_id = logger.add(
        lambda message: captured.append(str(message)),
        level="DEBUG",
        backtrace=True,
        diagnose=True,
    )
    try:
        entry = _models()["DataSourceEntry"]  # noqa: F841 - referenced in traceback
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("failed while handling entry")
    finally:
        logger.remove(sink_id)

    combined = "\n".join(captured)
    assert SECRET_TOKEN not in combined, "secret leaked through loguru diagnose=True"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://user:tok@host/path", "https://***@host/path"),
        ("https://x-access-token:tok@github.com/o/r.git", "https://***@github.com/o/r.git"),
        ("https://host:8443/p?q=1", "https://host:8443/p?q=1"),
        ("http://plain.example.com/data", "http://plain.example.com/data"),
    ],
)
def test_redact_url(url, expected):
    redacted = redact_url(url)
    assert redacted == expected
    assert "tok" not in redacted


def test_redact_url_in_text():
    """Git command errors embed the (credentialed) repo URL in free text."""
    url = "https://x-access-token:SECRETTOKEN@github.com/org/repo.git"
    err = f"Cmd('git') failed: fatal: could not read from '{url}'"
    scrubbed = redact_url_in_text(err, url)
    assert "SECRETTOKEN" not in scrubbed
    assert "https://***@github.com/org/repo.git" in scrubbed
