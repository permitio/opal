"""Config parse errors, printed configs (``print-config``) and ``--help`` never
render sensitive values."""

import json
import traceback
from enum import Enum
from typing import Optional

import pytest
from click.testing import CliRunner
from opal_common.authentication.types import EncryptionKeyFormat
from opal_common.confi import Confi, confi
from pydantic import BaseModel

FAKE_KEY = "FAKE-KEY-123"
SOURCES_WITH_AUTH = {
    "url": "http://h",
    "headers": {"Authorization": f"Bearer {FAKE_KEY}"},
}


class _Source(BaseModel):
    url: str
    headers: dict
    retries: int = 0


class _KeyFormat(str, Enum):
    pem = "pem"


class _SampleConfig(Confi):
    SOURCE = confi.model("SOURCE", _Source, {"url": "http://h", "headers": {}})
    # flagged explicitly - the name alone would not mark these
    UPSTREAM_CREDENTIAL = confi.str(
        "UPSTREAM_CREDENTIAL", "dev-placeholder", sensitive=True
    )
    SIGNING_SETTINGS = confi.model(
        "SIGNING_SETTINGS",
        _Source,
        {"url": "http://signer", "headers": {"X-Signature-Key": "dev-placeholder"}},
        sensitive=True,
    )
    DELAYED_CREDENTIAL = confi.delay(
        lambda: confi.str("DELAYED_CREDENTIAL", None, sensitive=True)
    )
    # caught by the name fallback
    SERVICE_API_KEY = confi.str("SERVICE_API_KEY", None)
    WEBHOOK_PASSPHRASE = confi.str("WEBHOOK_PASSPHRASE", "")
    EXCLUDE_PASSWORDS = confi.bool("EXCLUDE_PASSWORDS", True)
    PRIVATE_KEY_FORMAT = confi.enum("PRIVATE_KEY_FORMAT", _KeyFormat, _KeyFormat.pem)
    SIGNING_PRIVATE_KEY = confi.private_key(
        "SIGNING_PRIVATE_KEY", None, key_format=EncryptionKeyFormat.pem
    )
    # not sensitive
    REPO_URL = confi.str("REPO_URL", "https://example.com/repo.git")
    LOG_LEVEL = confi.str("LOG_LEVEL", "INFO")


def _load_error(monkeypatch, raw_value: str) -> ValueError:
    monkeypatch.setenv("SAMPLE_SOURCE", raw_value)
    with pytest.raises(ValueError) as exc_info:
        _SampleConfig(prefix="SAMPLE_")
    return exc_info.value


@pytest.mark.parametrize(
    "raw_value",
    [
        json.dumps({**SOURCES_WITH_AUTH, "retries": "many"}),
        json.dumps({"headers": f"Authorization: Bearer {FAKE_KEY}"}),
        # truncated JSON: the error's context holds the whole document
        json.dumps(SOURCES_WITH_AUTH)[:-2],
    ],
    ids=["invalid-field", "missing-field", "invalid-json"],
)
def test_invalid_model_value_error_omits_the_value(monkeypatch, raw_value):
    err = _load_error(monkeypatch, raw_value)

    rendered = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    assert FAKE_KEY not in rendered
    assert "SAMPLE_SOURCE" in str(err)


def test_invalid_model_value_error_names_the_failing_fields(monkeypatch):
    err = _load_error(monkeypatch, json.dumps({**SOURCES_WITH_AUTH, "retries": "x"}))

    assert str(err) == (
        "Failed parsing config key SAMPLE_SOURCE: "
        "1 validation error for _Source: retries (type_error.integer)"
    )


def _invoke_cli(*args: str):
    cli = _SampleConfig(prefix="SAMPLE_").get_cli_object()
    return CliRunner().invoke(cli, list(args), terminal_width=200)


def test_invalid_model_cli_option_error_omits_the_value():
    """For a bad option value, click prints the value (< 8.2) or str() of the
    error, which for a JSON decode error contains the value."""
    result = _invoke_cli("--source", json.dumps(SOURCES_WITH_AUTH)[:-2])

    assert result.exit_code != 0
    assert FAKE_KEY not in result.output
    assert "1 validation error for _Source: __root__ (value_error.jsondecode)" in (
        result.output
    )


def test_invalid_sensitive_cli_option_error_omits_the_value():
    result = _invoke_cli("--signing-private-key", FAKE_KEY)

    assert result.exit_code != 0
    assert FAKE_KEY not in result.output
    assert "could not be parsed (ValueError)" in result.output


def _sample_config(monkeypatch, **env: str) -> _SampleConfig:
    for key, value in env.items():
        monkeypatch.setenv(f"SAMPLE_{key}", value)
    return _SampleConfig(prefix="SAMPLE_")


SENSITIVE_ENV = {
    "UPSTREAM_CREDENTIAL": FAKE_KEY,
    "SIGNING_SETTINGS": json.dumps(
        {"url": "http://signer", "headers": {"X-Signature-Key": FAKE_KEY}}
    ),
    "DELAYED_CREDENTIAL": FAKE_KEY,
    "SERVICE_API_KEY": FAKE_KEY,
    "WEBHOOK_PASSPHRASE": FAKE_KEY,
    "REPO_URL": f"https://user:{FAKE_KEY}@example.com/repo.git?token={FAKE_KEY}",
}
SENSITIVE_ENTRIES = [
    "UPSTREAM_CREDENTIAL",
    "SIGNING_SETTINGS",
    "DELAYED_CREDENTIAL",
    "SERVICE_API_KEY",
    "WEBHOOK_PASSPHRASE",
]


def test_sensitive_is_set_by_the_flag_or_the_key_name(monkeypatch):
    entries = _sample_config(monkeypatch).entries

    assert [name for name in SENSITIVE_ENTRIES if not entries[name].sensitive] == []
    assert not entries["REPO_URL"].sensitive
    assert not entries["LOG_LEVEL"].sensitive


def test_printed_config_redacts_sensitive_entries(monkeypatch):
    config = _sample_config(monkeypatch, **SENSITIVE_ENV)

    printed = json.loads(repr(config))
    assert {name: printed[name] for name in SENSITIVE_ENTRIES} == dict.fromkeys(
        SENSITIVE_ENTRIES, "<redacted>"
    )
    assert printed["REPO_URL"] == "https://***@example.com/repo.git?token=***"
    assert printed["LOG_LEVEL"] == "INFO"
    assert FAKE_KEY not in str(config)
    # the config still holds the real values
    assert config.UPSTREAM_CREDENTIAL == FAKE_KEY


def test_debug_repr_redacts_sensitive_entries(monkeypatch):
    printed = _sample_config(monkeypatch, **SENSITIVE_ENV).debug_repr()

    assert FAKE_KEY not in printed
    for name in SENSITIVE_ENTRIES:
        assert f"    {name}: <redacted>\n" in printed
    assert "    REPO_URL: 'https://***@example.com/repo.git?token=***'\n" in printed
    assert "    LOG_LEVEL: 'INFO'\n" in printed


def test_printed_config_keeps_values_that_hold_no_credential(monkeypatch):
    printed = json.loads(repr(_sample_config(monkeypatch)))

    # a code default is still a value
    assert printed["UPSTREAM_CREDENTIAL"] == "<redacted>"
    # unset, empty, flag and enum entries named like credentials stay readable
    assert printed["DELAYED_CREDENTIAL"] == "None"
    assert printed["SERVICE_API_KEY"] == "None"
    assert printed["WEBHOOK_PASSPHRASE"] == ""
    assert printed["EXCLUDE_PASSWORDS"] == "True"
    assert printed["PRIVATE_KEY_FORMAT"] == str(_KeyFormat.pem)
    assert printed["REPO_URL"] == "https://example.com/repo.git"


def test_help_does_not_show_sensitive_defaults(monkeypatch):
    """For a non-str default, click shows the value resolved from the
    environment; for a str one, the code default."""
    cli = _sample_config(monkeypatch, **SENSITIVE_ENV).get_cli_object()

    result = CliRunner().invoke(cli, ["--help"], terminal_width=200)

    assert result.exit_code == 0, result.output
    assert FAKE_KEY not in result.output
    assert "dev-placeholder" not in result.output
    assert "[default: (<redacted>)]" in result.output
    assert "[default: (INFO)]" in result.output
    # only the two flagged entries with a default; an enum named like a
    # credential holds none (rendered "pem" or "_KeyFormat.pem" by Python version)
    assert result.output.count("<redacted>") == 2
    assert "pem)]" in result.output


def test_sensitive_is_not_passed_to_the_value_lookup():
    """With ``is_model=False`` the builders return the value directly."""
    eager = Confi(prefix="SAMPLE_", is_model=False)

    assert eager.str("NOT_SET", "fallback", sensitive=True) == "fallback"


@pytest.mark.parametrize(
    "name",
    [
        "OPAL_WS_TOKEN",
        "AUTH_PRIVATE_KEY_PASSPHRASE",
        "AUTH_PRIVATE_KEY",
        "AUTH_MASTER_TOKEN",
        "POLICY_REPO_SSH_KEY",
        "POLICY_BUNDLE_SERVER_TOKEN",
        "POLICY_BUNDLE_SERVER_TOKEN_ID",
        "POLICY_REPO_WEBHOOK_SECRET",
    ],
)
def test_server_credential_entries_are_sensitive(name):
    opal_server_config = pytest.importorskip("opal_server.config").opal_server_config

    assert opal_server_config.entries[name].sensitive


@pytest.mark.parametrize(
    "name",
    [
        "CLIENT_TOKEN",
        "POLICY_STORE_AUTH_TOKEN",
        "POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET",
    ],
)
def test_client_credential_entries_are_sensitive(name):
    from opal_client.config import opal_client_config

    assert opal_client_config.entries[name].sensitive


def test_server_print_config_masks_credentials(monkeypatch, capsys):
    print_config = pytest.importorskip("opal_server.cli").print_config
    from opal_server.config import opal_server_config

    monkeypatch.setattr(opal_server_config, "AUTH_MASTER_TOKEN", FAKE_KEY)
    monkeypatch.setattr(
        opal_server_config, "BROADCAST_URI", f"postgres://opal:{FAKE_KEY}@db/opal"
    )
    print_config()

    printed = capsys.readouterr().out
    assert FAKE_KEY not in printed
    assert "postgres://***@db/opal" in printed


def test_client_print_config_masks_credentials(monkeypatch, capsys):
    from opal_client.cli import print_config
    from opal_client.config import opal_client_config
    from opal_client.engine.options import CedarServerOptions

    monkeypatch.setattr(opal_client_config, "CLIENT_TOKEN", FAKE_KEY)
    monkeypatch.setattr(opal_client_config, "POLICY_STORE_AUTH_TOKEN", FAKE_KEY)
    monkeypatch.setattr(
        opal_client_config,
        "INLINE_CEDAR_CONFIG",
        CedarServerOptions(authentication="token", authentication_token=FAKE_KEY),
    )
    print_config()

    printed = capsys.readouterr().out
    assert FAKE_KEY not in printed
    assert '"CLIENT_TOKEN": "<redacted>"' in printed
