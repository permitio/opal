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

from typing import List

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
    """One instance of each credential-bearing model, all carrying
    SECRET_TOKEN."""
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
    """Repr() / str() (used by f-strings and ``"{}".format``) must never expose
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
    ``DataUpdate`` that hold ``DataSourceEntry`` objects.

    They carry no mixin themselves but must still redact via nested
    repr.
    """
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
    record (including ``extra``) as JSON.

    Interpolating or binding any of these models must not put the secret
    on the wire.
    """
    captured: List[str] = []
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
    tracebacks (the #901-class vector).

    The model's own value must render redacted.
    """
    captured: List[str] = []
    sink_id = logger.add(
        lambda message: captured.append(str(message)),
        level="DEBUG",
        backtrace=True,
        diagnose=True,
    )
    try:
        entry = _models()["DataSourceEntry"]
        try:
            # The raising line must *reference* ``entry`` (the whole model) so
            # loguru's diagnose renders its repr in the traceback - otherwise the
            # test is a tautology (an unprotected model would pass too). We must
            # NOT reach into a credential field here (e.g. ``entry.config[...]``):
            # diagnose evaluates that sub-expression and renders the raw dict,
            # which the model-layer mixin documents it cannot protect. Rendering
            # ``entry`` exercises exactly what the mixin defends.
            raise ValueError(entry)
        except ValueError:
            logger.exception("failed while handling entry")
    finally:
        logger.remove(sink_id)

    combined = "\n".join(captured)
    assert SECRET_TOKEN not in combined, "secret leaked through loguru diagnose=True"


@pytest.mark.parametrize(
    "url,expected",
    [
        # userinfo (user:password) is stripped
        ("https://user:tok@host/path", "https://***@host/path"),
        (
            "https://x-access-token:tok@github.com/o/r.git",
            "https://***@github.com/o/r.git",
        ),
        # username-only userinfo is still stripped (the user can be a token)
        ("ssh://gittok@host/repo.git", "ssh://***@host/repo.git"),
        # IPv6 literal must keep its brackets and stay a valid URL
        ("https://u:p@[::1]:8443/x", "https://***@[::1]:8443/x"),
        # sensitive query params are masked, non-sensitive kept
        (
            "https://host/p?token=secret&page=2",
            "https://host/p?token=***&page=2",
        ),
        ("https://host/p?access_token=secret", "https://host/p?access_token=***"),
        # sensitive params in the *fragment* are masked too
        ("https://host/p#access_token=secret", "https://host/p#access_token=***"),
        # non-sensitive params keep their exact original encoding (no urlencode
        # round-trip normalizing "%20" -> "+")
        (
            "https://host/p?name=John%20Doe&token=secret",
            "https://host/p?name=John%20Doe&token=***",
        ),
        # nothing sensitive -> returned byte-for-byte unchanged
        ("https://host:8443/p?q=1#frag", "https://host:8443/p?q=1#frag"),
        ("http://plain.example.com/data/", "http://plain.example.com/data/"),
        # scp-style git url has no parseable userinfo and no password -> untouched
        ("git@github.com:org/repo.git", "git@github.com:org/repo.git"),
        ("", ""),
    ],
)
def test_redact_url(url, expected):
    # expected values never contain a secret, so equality fully validates
    assert redact_url(url) == expected


def test_redact_url_never_raises_on_malformed_url():
    """redact_url is called from log/except paths and must never throw - e.g. an
    out-of-range port only raises when .port is accessed (urlsplit is lazy)."""
    bad = "https://u:p@host:99999999999/x"
    # would raise ValueError("Port out of range") without the guard
    assert redact_url(bad) == bad


def test_redact_url_in_text_masks_query_token_with_userinfo():
    """When a known URL carries *both* userinfo and a sensitive query param,
    the query token must still be masked (regression: the userinfo regex used
    to run first and destroy the verbatim URL before the query scrub could
    match)."""
    url = "https://user:SECRETTOK@host/path?token=SECRETTOK2"
    text = "fatal: could not read from '" + url + "'"
    scrubbed = redact_url_in_text(text, url)
    assert "SECRETTOK" not in scrubbed
    assert "SECRETTOK2" not in scrubbed
    assert "https://***@host/path?token=***" in scrubbed


def test_redact_url_in_text():
    """Git command errors embed the (credentialed) repo URL in free text."""
    url = "https://x-access-token:SECRETTOKEN@github.com/org/repo.git"
    err = f"Cmd('git') failed: fatal: could not read from '{url}'"
    scrubbed = redact_url_in_text(err, url)
    assert "SECRETTOKEN" not in scrubbed
    assert "https://***@github.com/org/repo.git" in scrubbed


def test_redact_url_in_text_scrubs_creds_not_in_known_url():
    """The regex scrub must catch a credentialed URL even when it differs from
    the URL we passed (e.g. git injected creds / normalized the string)."""
    # self.url has no creds, but git prints a credentialed variant
    text = (
        "fatal: could not read from 'https://x-access-token:LEAKED@github.com/o/r.git/'"
    )
    scrubbed = redact_url_in_text(text, "https://github.com/o/r.git")
    assert "LEAKED" not in scrubbed
    assert "https://***@github.com/o/r.git/" in scrubbed


def test_git_ssh_env_gates_verbose_tracing_on_log_diagnose(tmp_path):
    """On SSH clones GIT_TRACE/GIT_CURL_VERBOSE add verbose protocol/host
    disclosure to logs; they must only be set when LOG_DIAGNOSE is explicitly
    enabled."""
    from opal_common.config import opal_common_config
    from opal_common.git_utils import env

    ssh_url = "git@github.com:org/repo.git"
    original_diagnose = opal_common_config.LOG_DIAGNOSE
    original_key_file = opal_common_config.GIT_SSH_KEY_FILE
    # point the pem-file writer at a throwaway path so we never touch a real key
    opal_common_config.GIT_SSH_KEY_FILE = str(tmp_path / "id_test")
    try:
        opal_common_config.LOG_DIAGNOSE = False
        off = env.provide_git_ssh_environment(ssh_url, "DUMMY_KEY")
        assert "GIT_TRACE" not in off and "GIT_CURL_VERBOSE" not in off
        assert "GIT_SSH_COMMAND" in off

        opal_common_config.LOG_DIAGNOSE = True
        on = env.provide_git_ssh_environment(ssh_url, "DUMMY_KEY")
        assert on.get("GIT_TRACE") == "1" and on.get("GIT_CURL_VERBOSE") == "1"
    finally:
        opal_common_config.LOG_DIAGNOSE = original_diagnose
        opal_common_config.GIT_SSH_KEY_FILE = original_key_file


_URL_SECRET = "url-secret-must-not-leak"


@pytest.mark.parametrize(
    "model",
    [
        DataSourceEntry(
            url=f"https://user:{_URL_SECRET}@host/path?token={_URL_SECRET}",
            save_method="PUT",
        ),
        FetchEvent(
            fetcher="HttpFetchProvider",
            url=f"https://user:{_URL_SECRET}@host/path?token={_URL_SECRET}",
        ),
    ],
)
def test_url_field_credentials_redacted_in_repr(model):
    """The ``url`` field can embed credentials; repr/str must strip them (via
    redact_url) while keeping the host/path visible for debugging."""
    rendered = repr(model)
    assert _URL_SECRET not in rendered
    assert _URL_SECRET not in str(model)
    # host/path stay visible (we redact, not blanket-mask, urls)
    assert "***@host/path" in rendered


def test_url_field_wire_serialization_keeps_real_url():
    """Redaction is log-only: ``.dict()`` must keep the real (credentialed) url
    so fetching still works."""
    url = f"https://user:{_URL_SECRET}@host/path"
    entry = DataSourceEntry(url=url, save_method="PUT")
    assert entry.dict()["url"] == url
