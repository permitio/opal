"""Scope rendering and validation errors must mask git auth.

A Scope carries git auth (token / password / SSH private key) and a remote
URL that can embed auth. Its repr/str - what f-strings, ``{}`` log
interpolation and loguru's ``serialize=True`` sink render - must mask them,
and a ValidationError raised on bad scope input must not quote them.

``model_dump()`` is the wire / Redis format and must keep the real values.
"""

from typing import List

import pytest
from loguru import logger
from opal_common.schemas.policy_source import (
    GitHubTokenAuthData,
    GitPolicyScopeSource,
    SSHAuthData,
    UserPassAuthData,
)
from opal_common.schemas.scopes import Scope
from pydantic import ValidationError

FAKE_TOKEN = "FAKE-KEY-123"
FAKE_PASSWORD = "fakepass-FAKE-456"
FAKE_PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nFAKE-PRIVATE-KEY-789\n"
FAKE_URL_PASSWORD = "FAKE-URL-PASS-321"
FAKE_URL_TOKEN = "FAKE-URL-TOKEN-654"
REPO_URL = (
    f"https://fakeuser:{FAKE_URL_PASSWORD}@git.example.com/org/policy.git"
    f"?token={FAKE_URL_TOKEN}"
)
FAKE_VALUES = (
    FAKE_TOKEN,
    FAKE_PASSWORD,
    "FAKE-PRIVATE-KEY-789",
    FAKE_URL_PASSWORD,
    FAKE_URL_TOKEN,
)

AUTHS = {
    "token": GitHubTokenAuthData(token=FAKE_TOKEN),
    "userpass": UserPassAuthData(username="fakeuser", password=FAKE_PASSWORD),
    "ssh": SSHAuthData(username="git", private_key=FAKE_PRIVATE_KEY),
}


def _scope(auth) -> Scope:
    return Scope(
        scope_id="fake-scope",
        policy=GitPolicyScopeSource(source_type="git", url=REPO_URL, auth=auth),
    )


def _assert_absent(rendered: str):
    for value in FAKE_VALUES:
        assert value not in rendered, rendered


@pytest.mark.parametrize("auth_name", sorted(AUTHS))
def test_scope_repr_and_str_mask_auth_and_url(auth_name):
    scope = _scope(AUTHS[auth_name])

    for rendered in (repr(scope), str(scope), f"{scope}", "{}".format(scope)):
        _assert_absent(rendered)
        assert "<redacted>" in rendered
        # The URL stays useful for debugging: host and path are kept.
        assert "https://***@git.example.com/org/policy.git?token=***" in rendered


@pytest.mark.parametrize("auth_name", sorted(AUTHS))
def test_auth_model_repr_masks_its_own_field(auth_name):
    auth = AUTHS[auth_name]

    _assert_absent(repr(auth))
    _assert_absent(str(auth))
    assert "<redacted>" in repr(auth)


@pytest.mark.parametrize("auth_name", sorted(AUTHS))
def test_scope_wire_format_is_unchanged(auth_name):
    scope = _scope(AUTHS[auth_name])
    dumped = scope.model_dump()

    assert dumped["policy"]["url"] == REPO_URL
    assert dumped["policy"]["auth"] == AUTHS[auth_name].model_dump()
    assert Scope.model_validate_json(scope.model_dump_json()) == scope


def test_loguru_serialize_sink_masks_scope():
    captured: List[str] = []
    sink_id = logger.add(lambda m: captured.append(str(m)), serialize=True)
    try:
        for auth in AUTHS.values():
            logger.info("scope {scope}", scope=_scope(auth))
    finally:
        logger.remove(sink_id)

    assert len(captured) == len(AUTHS)
    _assert_absent("\n".join(captured))


BAD_SCOPE_INPUTS = {
    # userpass auth missing its username: the error quotes the whole auth dict
    "missing_username": {
        "auth_type": "userpass",
        "password": FAKE_PASSWORD,
    },
    # unknown discriminator: the error quotes the whole auth dict
    "unknown_auth_type": {
        "auth_type": "not-a-real-type",
        "password": FAKE_PASSWORD,
        "token": FAKE_TOKEN,
    },
    # wrong type for the SSH key itself
    "ssh_key_wrong_type": {
        "auth_type": "ssh",
        "username": "git",
        "private_key": ["FAKE-PRIVATE-KEY-789"],
    },
}


@pytest.mark.parametrize("case", sorted(BAD_SCOPE_INPUTS))
def test_scope_validation_error_does_not_quote_input(case):
    payload = {
        "scope_id": "fake-scope",
        "policy": {
            "source_type": "git",
            "url": REPO_URL,
            "auth": BAD_SCOPE_INPUTS[case],
        },
    }

    with pytest.raises(ValidationError) as exc_info:
        Scope.model_validate(payload)

    _assert_absent(str(exc_info.value))
    _assert_absent(repr(exc_info.value))


@pytest.mark.parametrize(
    "model,payload",
    [
        (UserPassAuthData, {"password": FAKE_PASSWORD}),
        (GitHubTokenAuthData, {"token": [FAKE_TOKEN]}),
        (SSHAuthData, {"private_key": FAKE_PRIVATE_KEY}),
        (
            GitPolicyScopeSource,
            {
                "url": REPO_URL,
                "auth": {"auth_type": "userpass", "password": FAKE_PASSWORD},
            },
        ),
    ],
)
def test_direct_model_validation_error_does_not_quote_input(model, payload):
    with pytest.raises(ValidationError) as exc_info:
        model.model_validate(payload)

    _assert_absent(str(exc_info.value))
