"""Masking of auth headers, tokens and sensitive query params in free text, and
the exception rendering used by log lines (``describe_error``)."""

import io
import json

import aiohttp
import pytest
from aiohttp.client_reqrep import ConnectionKey
from loguru import logger
from opal_common.http_utils import redact_sensitive_text, redact_url_in_text
from opal_common.logger import _scrub_record_message
from opal_common.logging_utils.errors import describe_error, describe_validation_error
from opal_common.logging_utils.scrubbing import CredentialScrubbingStream
from opal_common.tests.redaction_fixtures import (
    capture_logs,
    response_error,
    without_log_patcher,
)
from pydantic import BaseModel, ValidationError

FAKE_KEY = "FAKE-KEY-123"
# base64("fake-user:FAKE-KEY-123")
FAKE_BASIC = "ZmFrZS11c2VyOkZBS0UtS0VZLTEyMw=="


@pytest.fixture(autouse=True)
def _no_global_log_patcher():
    """The stream tests below check what the stream wrapper masks, so nothing
    may be masked before it (by the patcher an earlier ``configure_logs()``
    installed)."""
    with without_log_patcher():
        yield


@pytest.mark.parametrize(
    "text,expected",
    [
        ("GET http://h/p?token=FAKE-KEY-123 failed", "GET http://h/p?token=*** failed"),
        ("http://h/p?x=1&api_key=FAKE-KEY-123&y=2", "http://h/p?x=1&api_key=***&y=2"),
        ("http://h/p#access_token=FAKE-KEY-123", "http://h/p#access_token=***"),
        ("http://h/p;sig=FAKE-KEY-123", "http://h/p;sig=***"),
        ("url='http://h/p?TOKEN=FAKE-KEY-123'", "url='http://h/p?TOKEN=***'"),
        (
            '{"url": "http://h/?password=FAKE-KEY-123"}',
            '{"url": "http://h/?password=***"}',
        ),
    ],
)
def test_redact_url_in_text_masks_sensitive_query_params(text, expected):
    assert redact_url_in_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "http://h/p?page=2&monkey=1",  # "key" only as a suffix of another name
        "token=FAKE-KEY-123 without a separator before it",
        # already masked: the text right after the value stays
        "fetch http://h/p?token=***: TimeoutError",
        "",
    ],
)
def test_redact_url_in_text_keeps_text_without_sensitive_params(text):
    assert redact_url_in_text(text) == text


MASKED_CASES = [
    # aiohttp's RequestInfo renders headers as a CIMultiDictProxy repr
    (
        "<CIMultiDictProxy('Authorization': 'Bearer FAKE-KEY-123')>",
        "<CIMultiDictProxy('Authorization': '***')>",
    ),
    (
        "{'authorization': 'FAKE-KEY-123', 'accept': 'json'}",
        "{'authorization': '***', 'accept': 'json'}",
    ),
    ('{"Authorization": "FAKE-KEY-123"}', '{"Authorization": "***"}'),
    # JSON embedded in a JSON string (a serialized log record's "text")
    (
        '{"text": "{\\"Authorization\\": \\"FAKE-KEY-123\\"}"}',
        '{"text": "{\\"Authorization\\": \\"***\\"}"}',
    ),
    (
        "Proxy-Authorization: Basic " + FAKE_BASIC + "\nHost: h",
        "Proxy-Authorization: ***\nHost: h",
    ),
    ("authorization: FAKE-KEY-123", "authorization: ***"),
    ("Authorization: ***: rejected", "Authorization: ***: rejected"),
    ("sent bearer FAKE-KEY-123 to h", "sent bearer *** to h"),
    # a lowercase word of 16+ characters is a credential, not prose
    ("sent Bearer abcdefghijklmnop to h", "sent Bearer *** to h"),
    ("sent Basic " + FAKE_BASIC + " to h", "sent Basic *** to h"),
    (
        "fatal: https://user:FAKE-KEY-123@h/r.git?access_token=FAKE-KEY-123",
        "fatal: https://***@h/r.git?access_token=***",
    ),
]


@pytest.mark.parametrize("text,expected", MASKED_CASES)
def test_redact_sensitive_text_masks_credentials(text, expected):
    assert redact_sensitive_text(text) == expected


@pytest.mark.parametrize("text,expected", MASKED_CASES)
def test_redact_sensitive_text_is_idempotent(text, expected):
    assert redact_sensitive_text(redact_sensitive_text(text)) == expected


def test_redact_sensitive_text_masks_real_aiohttp_error_repr():
    err = response_error({"Authorization": f"Bearer {FAKE_KEY}"})
    assert FAKE_KEY in repr(err)  # what the redaction is for

    assert FAKE_KEY not in redact_sensitive_text(repr(err))


@pytest.mark.parametrize(
    "text",
    [
        "Bearer token is not valid!",
        "Basic handler to queue a fetch event",
        "Bearer abcdefghijklmno is fifteen letters",
        "opa run --authorization=basic --authentication=token",
        "Authorization header is required!",
    ],
)
def test_redact_sensitive_text_keeps_prose_and_flags(text):
    assert redact_sensitive_text(text) == text


@pytest.mark.parametrize(
    "value",
    [None, "", 42, b"Bearer FAKE-KEY-123", '"Authorization": "FAKE', "Bearer", "\\"],
)
def test_redact_sensitive_text_never_raises(value):
    result = redact_sensitive_text(value)
    if not isinstance(value, str) or not value:
        assert result is value


def _connector_error_with_proxy_auth() -> aiohttp.ClientConnectorError:
    # the ConnectionKey field set differs between aiohttp versions
    fields = dict.fromkeys(ConnectionKey._fields)
    fields.update(
        host="h",
        port=443,
        is_ssl=True,
        ssl=True,
        proxy_auth=aiohttp.BasicAuth("fake-user", FAKE_KEY),
    )
    return aiohttp.ClientConnectorError(
        ConnectionKey(**fields), OSError(61, "Connection refused")
    )


@pytest.mark.filterwarnings("ignore:BasicAuth is deprecated:DeprecationWarning")
@pytest.mark.parametrize(
    "make_error",
    [
        lambda: response_error({"Authorization": f"Bearer {FAKE_KEY}"}),
        lambda: response_error(
            {"Authorization": f"Bearer {FAKE_KEY}"},
            error_type=aiohttp.ContentTypeError,
        ),
        _connector_error_with_proxy_auth,
        lambda: RuntimeError(f"GET https://user:{FAKE_KEY}@h/p?token={FAKE_KEY}"),
        lambda: RuntimeError(f"sent Authorization: Bearer {FAKE_KEY}"),
    ],
    ids=[
        "ClientResponseError",
        "ContentTypeError",
        "ClientConnectorError",
        "url",
        "header",
    ],
)
def test_describe_error_never_renders_credentials(make_error):
    err = make_error()
    assert FAKE_KEY in repr(err)  # what describe_error replaces

    described = describe_error(err)

    assert FAKE_KEY not in described
    assert described.startswith(f"{type(err).__name__}: ")


def test_describe_error_keeps_the_useful_parts():
    err = response_error({"Authorization": f"Bearer {FAKE_KEY}"}, status=502)

    assert describe_error(err) == (
        "ClientResponseError: 502, message='Bad Gateway', "
        "url='http://example.com/v1/data'"
    )


def test_describe_error_without_message_is_the_type_name():
    assert describe_error(TimeoutError()) == "TimeoutError"


class _Entry(BaseModel):
    url: str
    headers: dict


def _validation_error() -> ValidationError:
    with pytest.raises(ValidationError) as exc_info:
        _Entry(url="http://h", headers=f"Authorization: Bearer {FAKE_KEY}")
    return exc_info.value


def test_describe_validation_error_omits_the_input():
    err = _validation_error()
    assert FAKE_KEY in str(err)  # pydantic v2 renders input_value by default

    assert describe_validation_error(err) == (
        "1 validation error for _Entry: headers (dict_type)"
    )
    assert FAKE_KEY not in describe_error(err)


def test_describe_validation_error_lists_every_location():
    with pytest.raises(ValidationError) as exc_info:
        _Entry.model_validate_json('{"headers": [1]}')

    assert describe_validation_error(exc_info.value) == (
        "2 validation errors for _Entry: url (missing); headers (dict_type)"
    )


def test_describe_validation_error_on_invalid_json_omits_the_document():
    with pytest.raises(ValidationError) as exc_info:
        _Entry.model_validate_json('{"headers": {"Authorization": "' + FAKE_KEY)

    described = describe_validation_error(exc_info.value)
    assert FAKE_KEY not in described
    assert "<root> (json_invalid)" in described


def test_log_patcher_masks_message_and_str_extra_values():
    """Every keyword argument of a log call lands in ``extra``, which a
    serialized sink writes even when the message does not reference it."""
    patched = logger.patch(_scrub_record_message)
    with capture_logs() as logs:
        patched.warning(
            "request failed: {err}",
            err=f"Authorization: Bearer {FAKE_KEY}",
            url=f"https://h/p?token={FAKE_KEY}",
        )

    assert FAKE_KEY not in logs.combined
    record = json.loads(logs.serialized[0])["record"]
    assert record["message"] == "request failed: Authorization: ***"
    assert record["extra"]["url"] == "https://h/p?token=***"


def test_log_patcher_leaves_non_str_extra_values_untouched():
    patched = logger.patch(_scrub_record_message)
    with capture_logs() as logs:
        patched.info("count {n}", n=3)

    assert json.loads(logs.serialized[0])["record"]["extra"] == {"n": 3}


def test_scrubbing_stream_masks_auth_header_of_serialized_extra():
    """The patcher leaves non-``str`` extra values alone; the stream wrapper
    masks them in the final serialized line, keeping it valid JSON."""
    buffer = io.StringIO()
    sink_id = logger.add(
        CredentialScrubbingStream(buffer), level="DEBUG", serialize=True
    )
    try:
        logger.info("calling callback", headers={"Authorization": f"Bearer {FAKE_KEY}"})
    finally:
        logger.remove(sink_id)

    line = buffer.getvalue()
    assert FAKE_KEY not in line
    assert json.loads(line)["record"]["extra"]["headers"] == {"Authorization": "***"}


def test_scrubbing_stream_masks_auth_header_in_traceback():
    buffer = io.StringIO()
    sink_id = logger.add(
        CredentialScrubbingStream(buffer),
        level="DEBUG",
        backtrace=True,
        diagnose=False,
        colorize=False,
    )
    try:
        try:
            raise RuntimeError(repr(response_error({"Authorization": FAKE_KEY})))
        except RuntimeError:
            logger.exception("request failed")
    finally:
        logger.remove(sink_id)

    assert FAKE_KEY not in buffer.getvalue()
    assert "'Authorization': '***'" in buffer.getvalue()
