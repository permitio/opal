"""A config *model* is accepted where a plain ``dict`` is declared - and only
flattened when the field actually declares a ``dict``.

pydantic v1 coerced a BaseModel into a ``dict`` field via ``dict(model)``; v2
rejects it. The shim restores that, but it must not fire on subclasses that
re-declare ``config`` with a concrete model type: v1 never re-validated an
instance there, and flattening it silently drops subclass-only fields and blanks
alias-only ones - leaving a provider fetching with empty credentials.
"""

from typing import Optional

import pytest
from opal_common.fetcher.events import FetcherConfig, FetchEvent
from opal_common.fetcher.providers.http_fetch_provider import (
    HttpFetcherConfig,
    HttpFetchEvent,
    HttpMethods,
)
from opal_common.schemas.data import (
    DataSourceConfig,
    DataSourceEntry,
    DataSourceEntryWithPollingInterval,
)
from pydantic import Field


class _ExtendedConfig(HttpFetcherConfig):
    """A third-party config that adds a field on top of the declared type."""

    extra_field: str


class _AliasedConfig(FetcherConfig):
    """A third-party config whose fields are populated by alias only."""

    connection_params: Optional[dict] = Field(None, alias="connectionParams")
    api_key: Optional[str] = Field(None, alias="apiKey")


class _AliasedEvent(FetchEvent):
    fetcher: str = "PostgresFetchProvider"
    config: Optional[_AliasedConfig] = None


# --- the case the shim exists for: a model where a dict is declared -----------


def test_base_fetch_event_accepts_a_config_model():
    """``FetchingEngine.queue_url(url, callback, HttpFetcherConfig(...))``."""
    event = FetchEvent(
        url="http://example.com",
        fetcher="HttpFetchProvider",
        config=HttpFetcherConfig(headers={"Authorization": "Bearer x"}),
    )

    assert isinstance(event.config, dict)
    assert event.config["headers"] == {"Authorization": "Bearer x"}


def test_data_source_entry_accepts_a_config_model():
    """The pattern documented in ``configure_external_data_sources.mdx``."""
    entry = DataSourceEntry(
        url="http://backend/v1/policy/config",
        topics=["policy_data"],
        config=HttpFetcherConfig(headers={"Authorization": "Bearer secret"}),
    )

    assert isinstance(entry.config, dict)
    assert entry.config["headers"] == {"Authorization": "Bearer secret"}


def test_data_source_config_accepts_base_entries():
    """The full documented sample: base entries nested in a DataSourceConfig.

    ``entries`` declares the ``DataSourceEntryWithPollingInterval`` subclass,
    so a plain ``DataSourceEntry`` instance is not an instance of the declared
    type - v2 rejects it where v1 read its fields.
    """
    entry = DataSourceEntry(
        url="http://backend/v1/policy/config",
        topics=["policy_data"],
        config=HttpFetcherConfig(headers={"Authorization": "Bearer secret"}),
    )

    config = DataSourceConfig(entries=[entry])

    assert config.entries[0].url == entry.url
    assert config.entries[0].topics == ["policy_data"]
    assert config.entries[0].config == entry.config
    assert config.entries[0].periodic_update_interval is None


def test_data_source_config_preserves_polling_entries():
    entry = DataSourceEntryWithPollingInterval(
        url="http://x", periodic_update_interval=42.0
    )

    config = DataSourceConfig(entries=[entry])

    assert config.entries[0].periodic_update_interval == 42.0


def test_data_source_config_still_accepts_dicts():
    config = DataSourceConfig(entries=[{"url": "http://x", "topics": ["t"]}])

    assert config.entries[0].url == "http://x"
    assert config.entries[0].topics == ["t"]


def test_plain_dict_config_is_untouched():
    entry = DataSourceEntry(url="http://x", config={"headers": {"a": "b"}})

    assert entry.config == {"headers": {"a": "b"}}


def test_none_config_is_untouched():
    assert FetchEvent(url="http://x", fetcher="f", config=None).config is None


# --- the case the shim must NOT fire on: a declared model type ----------------


def test_subclass_config_keeps_its_extra_fields():
    event = HttpFetchEvent(
        url="http://example.com",
        fetcher="HttpFetchProvider",
        config=_ExtendedConfig(extra_field="keepme", headers={"a": "b"}),
    )

    assert isinstance(event.config, _ExtendedConfig)
    assert event.config.extra_field == "keepme"
    assert event.config.headers == {"a": "b"}


def test_alias_only_config_is_not_blanked():
    """``dict(model)`` yields field names, which an alias-only model cannot read
    back - so re-validating would silently drop these to their defaults."""
    config = _AliasedConfig(
        connectionParams={"dsn": "postgres://host/db"}, apiKey="SECRET-KEY"
    )

    event = _AliasedEvent(url="postgres://host/db", config=config)

    assert event.config.connection_params == {"dsn": "postgres://host/db"}
    assert event.config.api_key == "SECRET-KEY"


def test_declared_model_type_config_passes_through_intact():
    config = HttpFetcherConfig(headers={"Authorization": "Bearer x"})

    event = HttpFetchEvent(url="http://example.com", config=config)

    assert isinstance(event.config, HttpFetcherConfig)
    assert event.config.headers == {"Authorization": "Bearer x"}


def test_declared_model_type_still_accepts_a_mapping():
    event = HttpFetchEvent(url="http://example.com", config={"headers": {"a": "b"}})

    assert isinstance(event.config, HttpFetcherConfig)
    assert event.config.headers == {"a": "b"}


@pytest.mark.parametrize("method", ["post", HttpMethods.POST])
def test_declared_model_type_preserves_enum_fields(method):
    event = HttpFetchEvent(
        url="http://example.com",
        config=HttpFetcherConfig(headers={"a": "b"}, method=method),
    )

    assert event.config.method == HttpMethods.POST
