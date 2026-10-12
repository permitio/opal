import asyncio

import pytest

from opal_server.config import opal_server_config
from opal_server.policy.watcher import manifest as manifest_module
from opal_server.policy.watcher.manifest import (
    PolicyBundleManifestFetcher,
    PolicyBundleSourceRegistry,
)
from opal_server.policy.watcher.task import MultiPolicyWatcherTask


class _Response:
    def __init__(self, status, headers=None, payload=None):
        self.status = status
        self.headers = headers or {}
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self):
        return self.payload


class _Session:
    def __init__(self, request, response):
        self.request = request
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def get(self, url, headers):
        self.request.append((url, headers))
        return self.response


@pytest.mark.asyncio
async def test_manifest_fetcher_uses_bearer_auth_and_etag(monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "POLICY_BUNDLE_MANIFEST_URL", "https://example.test/manifest"
    )
    monkeypatch.setattr(
        opal_server_config, "POLICY_BUNDLE_MANIFEST_REQUEST_TIMEOUT", 10
    )
    monkeypatch.setattr(
        opal_server_config, "POLICY_BUNDLE_MANIFEST_SERVER_TYPE", "HTTP"
    )
    monkeypatch.setattr(
        opal_server_config, "POLICY_BUNDLE_MANIFEST_SERVER_TOKEN", "secret"
    )
    requested = []
    responses = [
        _Response(
            200,
            headers={"ETag": '"manifest-v1"'},
            payload={
                "sources": [
                    {"source_id": "team-a", "url": "https://example.test/a"}
                ]
            },
        ),
        _Response(304),
    ]
    monkeypatch.setattr(
        manifest_module.aiohttp,
        "ClientSession",
        lambda **kwargs: _Session(requested, responses.pop(0)),
    )

    async def accept_status(response, expected, logger):
        return None

    monkeypatch.setattr(manifest_module, "throw_if_bad_status_code", accept_status)
    fetcher = PolicyBundleManifestFetcher()

    sources, etag = await fetcher.fetch()
    unchanged, unchanged_etag = await fetcher.fetch()

    assert [source.source_id for source in sources.sources] == ["team-a"]
    assert etag == '"manifest-v1"'
    assert unchanged is None
    assert unchanged_etag == etag
    assert requested[0][1]["Authorization"] == "Bearer secret"
    assert requested[1][1]["If-None-Match"] == etag


def test_aws_manifest_auth_requires_access_key_and_secret(monkeypatch):
    monkeypatch.setattr(
        opal_server_config, "POLICY_BUNDLE_MANIFEST_URL", "https://s3.example.test/manifest"
    )
    monkeypatch.setattr(
        opal_server_config, "POLICY_BUNDLE_MANIFEST_REQUEST_TIMEOUT", 10
    )
    monkeypatch.setattr(
        opal_server_config, "POLICY_BUNDLE_MANIFEST_SERVER_TYPE", "AWS-S3"
    )
    monkeypatch.setattr(
        opal_server_config, "POLICY_BUNDLE_MANIFEST_SERVER_TOKEN", None
    )
    monkeypatch.setattr(
        opal_server_config, "POLICY_BUNDLE_MANIFEST_SERVER_TOKEN_ID", None
    )

    with pytest.raises(ValueError, match="requires both token and token ID"):
        PolicyBundleManifestFetcher()


@pytest.mark.asyncio
async def test_registry_retains_last_known_good_sources_on_refresh_error():
    class _Fetcher:
        def __init__(self):
            self.results = [
                (
                    manifest_module.ApiPolicyBundleSources(
                        sources=[
                            {
                                "source_id": "team-a",
                                "url": "https://example.test/a",
                            }
                        ]
                    ),
                    '"v1"',
                ),
                RuntimeError("manifest server is unavailable"),
            ]

        async def fetch(self):
            result = self.results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    registry = object.__new__(PolicyBundleSourceRegistry)
    registry.fetcher = _Fetcher()
    registry.refresh_interval = 60
    registry._sources = None
    registry._last_error = None
    registry._last_refresh = 0
    registry._lock = asyncio.Lock()

    initial = await registry.get_sources(force=True)
    retained = await registry.get_sources(force=True)

    assert initial is retained
    assert [source.source_id for source in retained.sources] == ["team-a"]


@pytest.mark.asyncio
async def test_manifest_reconciliation_only_replaces_changed_sources():
    class _Source:
        def __init__(self):
            self.stopped = False

        async def stop(self):
            self.stopped = True

    source_a = _Source()
    source_b = _Source()
    config_a = manifest_module.ApiPolicyBundleSources(
        sources=[{"source_id": "team-a", "url": "https://example.test/a"}]
    ).sources[0]
    config_b = manifest_module.ApiPolicyBundleSources(
        sources=[{"source_id": "team-b", "url": "https://example.test/b"}]
    ).sources[0]
    task = object.__new__(MultiPolicyWatcherTask)
    task._policy_sources = {"team-a": source_a}
    task._source_configs = {"team-a": config_a}
    task._source_tasks = {}
    task._source_factory = lambda config: source_b
    task._reconcile_lock = asyncio.Lock()
    started = []
    task._start_source = lambda source_id, source: started.append(source_id)

    await task._reconcile_sources([config_a, config_b])

    assert task._policy_sources == {"team-a": source_a, "team-b": source_b}
    assert task._policy_sources["team-a"] is source_a
    assert not source_a.stopped
    assert started == ["team-b"]

    await task._reconcile_sources([config_b])

    assert task._policy_sources == {"team-b": source_b}
    assert source_a.stopped


@pytest.mark.asyncio
async def test_manifest_reconciliation_replaces_changed_source_definition():
    class _Source:
        def __init__(self):
            self.stopped = False

        async def stop(self):
            self.stopped = True

    old_source = _Source()
    replacement = _Source()
    old_config = manifest_module.ApiPolicyBundleSources(
        sources=[{"source_id": "team-a", "url": "https://example.test/a"}]
    ).sources[0]
    updated_config = manifest_module.ApiPolicyBundleSources(
        sources=[{"source_id": "team-a", "url": "https://example.test/a-v2"}]
    ).sources[0]
    task = object.__new__(MultiPolicyWatcherTask)
    task._policy_sources = {"team-a": old_source}
    task._source_configs = {"team-a": old_config}
    task._source_tasks = {}
    task._source_factory = lambda config: replacement
    task._reconcile_lock = asyncio.Lock()
    started = []
    task._start_source = lambda source_id, source: started.append(source)

    await task._reconcile_sources([updated_config])

    assert old_source.stopped
    assert task._policy_sources["team-a"] is replacement
    assert started == [replacement]


@pytest.mark.asyncio
async def test_manifest_watcher_dispatches_stable_webhook_by_source_id():
    class _Source:
        def __init__(self):
            self.triggers = 0

        async def check_for_changes(self):
            self.triggers += 1

    source_a = _Source()
    source_b = _Source()

    class _Registry:
        async def get_sources(self, force=False):
            return manifest_module.ApiPolicyBundleSources(
                sources=[
                    {"source_id": "team-a", "url": "https://example.test/a"},
                    {"source_id": "team-b", "url": "https://example.test/b"},
                ]
            )

    task = object.__new__(MultiPolicyWatcherTask)
    task._manifest_registry = _Registry()
    task._policy_sources = {"team-a": source_a, "team-b": source_b}
    task._source_configs = {
        source.source_id: source
        for source in manifest_module.ApiPolicyBundleSources(
            sources=[
                {"source_id": "team-a", "url": "https://example.test/a"},
                {"source_id": "team-b", "url": "https://example.test/b"},
            ]
        ).sources
    }
    task._source_tasks = {}
    task._source_factory = lambda config: None
    task._reconcile_lock = asyncio.Lock()
    task._start_source = lambda source_id, source: None

    await task.trigger("webhook", {"source_id": "team-b"})

    assert source_a.triggers == 0
    assert source_b.triggers == 1


def test_manifest_rejects_overlapping_resolved_paths():
    sources = manifest_module.ApiPolicyBundleSources(
        sources=[
            {
                "source_id": "team-a",
                "url": "https://example.test/a",
                "clone_path": "/tmp/shared",
                "tmp_path": "/tmp/shared/bundle.tar.gz",
            },
        ]
    )

    with pytest.raises(ValueError, match="must not overlap"):
        manifest_module.validate_resolved_source_paths(sources.sources)