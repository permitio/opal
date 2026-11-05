"""Credential-bearing models keep sensitive values out of ValidationError text
and out of repr/str, without changing their wire form."""

import json
from types import SimpleNamespace

import pytest
from opal_common.fetcher.events import FetcherConfig, FetchEvent
from opal_common.fetcher.providers.http_fetch_provider import (
    HttpFetcherConfig,
    HttpFetchEvent,
)
from opal_common.schemas.data import (
    CallbackEntry,
    DataEntryReport,
    DataSourceConfig,
    DataSourceEntry,
    DataSourceEntryWithPollingInterval,
    DataUpdate,
    DataUpdateReport,
    ServerDataSourceConfig,
    UpdateCallback,
)
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.security import AccessToken
from pydantic import ValidationError

FAKE_KEY = "FAKE-KEY-123"
AUTH_CONFIG = {"headers": {"Authorization": f"Bearer {FAKE_KEY}"}}
# each payload carries FAKE_KEY and fails validation
INVALID_PAYLOADS = [
    (DataSourceEntry, {"config": AUTH_CONFIG}),
    (
        DataSourceEntryWithPollingInterval,
        {"url": "http://h", "periodic_update_interval": FAKE_KEY},
    ),
    (DataSourceConfig, {"entries": [{"config": AUTH_CONFIG}]}),
    (ServerDataSourceConfig, {"config": {"entries": [{"config": AUTH_CONFIG}]}}),
    (DataUpdate, {"entries": [{"url": "http://h", "config": FAKE_KEY}]}),
    (CallbackEntry, {"url": "http://h", "config": {"headers": FAKE_KEY}}),
    (UpdateCallback, {"callbacks": [["http://h", {"headers": FAKE_KEY}]]}),
    (DataEntryReport, {"entry": {"config": AUTH_CONFIG}}),
    (DataUpdateReport, {"reports": [{"entry": {"config": AUTH_CONFIG}}]}),
    (FetcherConfig, {"fetcher": {"token": FAKE_KEY}}),
    (HttpFetcherConfig, {"headers": f"Bearer {FAKE_KEY}"}),
    (FetchEvent, {"url": f"http://h/?token={FAKE_KEY}"}),
    (HttpFetchEvent, {"url": "http://h", "config": {"headers": FAKE_KEY}}),
    (PolicyBundle, {"manifest": [], "hash": "h", "data_modules": FAKE_KEY}),
]


@pytest.mark.parametrize(
    "model,payload", INVALID_PAYLOADS, ids=[m.__name__ for m, _ in INVALID_PAYLOADS]
)
def test_validation_error_text_omits_the_input(model, payload):
    with pytest.raises(ValidationError) as exc_info:
        model.model_validate(payload)
    # the structured errors still carry the input - only the text hides it
    assert FAKE_KEY in json.dumps(exc_info.value.errors(include_url=False), default=str)

    for rendered in (str(exc_info.value), repr(exc_info.value)):
        assert FAKE_KEY not in rendered
        assert "input_value" not in rendered


@pytest.mark.parametrize(
    "model,payload", INVALID_PAYLOADS, ids=[m.__name__ for m, _ in INVALID_PAYLOADS]
)
def test_validation_error_from_json_omits_the_input(model, payload):
    with pytest.raises(ValidationError) as exc_info:
        model.model_validate_json(json.dumps(payload))

    assert FAKE_KEY not in str(exc_info.value)


def test_hiding_input_keeps_existing_model_config():
    """``PolicyBundle`` still validates from attributes (its base config), and
    a subclass's own config merges with the inherited setting."""
    bundle = PolicyBundle.model_validate(
        SimpleNamespace(manifest=[], hash="h", data_modules=[], policy_modules=[]),
    )
    assert bundle.hash == "h"
    assert HttpFetcherConfig.model_config["use_enum_values"] is True
    assert HttpFetcherConfig.model_config["hide_input_in_errors"] is True


CREDENTIALED_URL = f"https://user:{FAKE_KEY}@host/path?token={FAKE_KEY}"


@pytest.mark.parametrize(
    "model",
    [
        CallbackEntry(url=CREDENTIALED_URL),
        UpdateCallback(callbacks=[CREDENTIALED_URL]),
        UpdateCallback(
            callbacks=[(CREDENTIALED_URL, HttpFetcherConfig(**AUTH_CONFIG))]
        ),
        ServerDataSourceConfig(external_source_url=CREDENTIALED_URL),
        DataUpdate(
            entries=[],
            callback=UpdateCallback(
                callbacks=[(CREDENTIALED_URL, HttpFetcherConfig(**AUTH_CONFIG))]
            ),
        ),
    ],
    ids=[
        "CallbackEntry",
        "UpdateCallback-url",
        "UpdateCallback-tuple",
        "ServerDataSourceConfig",
        "DataUpdate",
    ],
)
def test_callback_and_source_urls_are_redacted_in_repr(model):
    for rendered in (repr(model), str(model), f"{model}"):
        assert FAKE_KEY not in rendered
        assert "***@host/path?token=***" in rendered


def test_access_token_is_redacted_in_repr():
    token = AccessToken(token=FAKE_KEY)

    assert FAKE_KEY not in repr(token)
    assert FAKE_KEY not in str(token)
    assert token.model_dump()["token"] == FAKE_KEY


def test_url_redaction_does_not_change_the_wire_form():
    callbacks = UpdateCallback(
        callbacks=[CREDENTIALED_URL, (CREDENTIALED_URL, HttpFetcherConfig())]
    )
    source = ServerDataSourceConfig(external_source_url=CREDENTIALED_URL)

    assert callbacks.model_dump()["callbacks"][0] == CREDENTIALED_URL
    assert callbacks.model_dump()["callbacks"][1][0] == CREDENTIALED_URL
    assert CallbackEntry(url=CREDENTIALED_URL).model_dump()["url"] == CREDENTIALED_URL
    assert FAKE_KEY in source.model_dump_json()
