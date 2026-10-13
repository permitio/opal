"""Credential-bearing models keep sensitive values out of repr/str, without
changing their wire form."""

import pytest
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.schemas.data import (
    CallbackEntry,
    DataUpdate,
    ServerDataSourceConfig,
    UpdateCallback,
)
from opal_common.schemas.security import AccessToken

FAKE_KEY = "FAKE-KEY-123"
AUTH_CONFIG = {"headers": {"Authorization": f"Bearer {FAKE_KEY}"}}
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
    assert token.dict()["token"] == FAKE_KEY


def test_url_redaction_does_not_change_the_wire_form():
    callbacks = UpdateCallback(
        callbacks=[CREDENTIALED_URL, (CREDENTIALED_URL, HttpFetcherConfig())]
    )
    source = ServerDataSourceConfig(external_source_url=CREDENTIALED_URL)

    assert callbacks.dict()["callbacks"][0] == CREDENTIALED_URL
    assert callbacks.dict()["callbacks"][1][0] == CREDENTIALED_URL
    assert CallbackEntry(url=CREDENTIALED_URL).dict()["url"] == CREDENTIALED_URL
    assert FAKE_KEY in source.json()
