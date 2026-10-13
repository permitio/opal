from pathlib import Path

import pytest
from fastapi import HTTPException
from git import Repo
from opal_server.config import (
    ApiPolicyBundleSources,
    PolicySourceTypes,
    opal_server_config,
    validate_policy_bundle_source_mode,
)
from opal_server.policy.bundles import api as bundle_api
from opal_server.policy.bundles.api import get_repo
from opal_server.policy.watcher.task import MultiPolicyWatcherTask
from opal_server.policy.webhook import api as webhook_api
from pydantic import ValidationError
from starlette.requests import Request


def test_remote_manifest_mode_excludes_other_source_settings():
    validate_policy_bundle_source_mode(
        ApiPolicyBundleSources(), None, "https://example.test/manifest.json"
    )

    with pytest.raises(ValueError, match="Configure only one"):
        validate_policy_bundle_source_mode(
            ApiPolicyBundleSources(
                sources=[{"source_id": "team-a", "url": "https://example.test/a"}]
            ),
            None,
            "https://example.test/manifest.json",
        )

    with pytest.raises(ValueError, match="Configure only one"):
        validate_policy_bundle_source_mode(
            ApiPolicyBundleSources(),
            "https://example.test/bundle",
            "https://example.test/manifest.json",
        )


def test_bundle_sources_accept_independent_source_ids_and_paths():
    config = ApiPolicyBundleSources(
        sources=[
            {
                "source_id": "team-a",
                "url": "https://example.test/a",
                "filename": "team-a.tar.gz",
                "clone_path": "/tmp/team-a-repo",
                "tmp_path": "/tmp/team-a.tar.gz",
            },
            {
                "source_id": "team-b",
                "url": "https://example.test/b",
                "filename": "team-b.tar.gz",
                "clone_path": "/tmp/team-b-repo",
                "tmp_path": "/tmp/team-b.tar.gz",
            },
        ]
    )

    assert [source.source_id for source in config.sources] == ["team-a", "team-b"]


def test_bundle_sources_reject_duplicate_ids():
    with pytest.raises(ValidationError, match="source_id values must be unique"):
        ApiPolicyBundleSources(
            sources=[
                {"source_id": "team-a", "url": "https://example.test/a"},
                {"source_id": "team-a", "url": "https://example.test/b"},
            ]
        )


def test_bundle_sources_reject_shared_local_paths():
    with pytest.raises(
        ValidationError, match="configured clone_path values must be unique"
    ):
        ApiPolicyBundleSources(
            sources=[
                {
                    "source_id": "team-a",
                    "url": "https://example.test/a",
                    "clone_path": "/tmp/shared",
                },
                {
                    "source_id": "team-b",
                    "url": "https://example.test/b",
                    "clone_path": "/tmp/shared",
                },
            ]
        )


def test_bundle_sources_reject_path_like_filenames():
    with pytest.raises(ValidationError, match="plain filename"):
        ApiPolicyBundleSources(
            sources=[
                {
                    "source_id": "team-a",
                    "url": "https://example.test/a",
                    "filename": "../bundle.tar.gz",
                }
            ]
        )


@pytest.mark.asyncio
async def test_bundle_repository_lookup_uses_selected_source_path(
    monkeypatch, tmp_path
):
    source_path = tmp_path / "team-a-repository"
    Repo.init(source_path)
    monkeypatch.setattr(
        opal_server_config,
        "POLICY_BUNDLE_SOURCES",
        ApiPolicyBundleSources(
            sources=[
                {
                    "source_id": "team-a",
                    "url": "https://example.test/a",
                    "clone_path": str(source_path),
                },
                {
                    "source_id": "team-b",
                    "url": "https://example.test/b",
                    "clone_path": str(tmp_path / "team-b-repository"),
                },
            ]
        ),
    )

    repo = await get_repo(
        base_clone_path=str(tmp_path),
        clone_subdirectory_prefix="source",
        use_fixed_path=False,
        source_id="team-a",
    )

    assert Path(repo.working_tree_dir) == source_path


@pytest.mark.asyncio
async def test_bundle_repository_lookup_requires_source_for_multiple_sources(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        opal_server_config,
        "POLICY_BUNDLE_SOURCES",
        ApiPolicyBundleSources(
            sources=[
                {"source_id": "team-a", "url": "https://example.test/a"},
                {"source_id": "team-b", "url": "https://example.test/b"},
            ]
        ),
    )

    with pytest.raises(HTTPException) as error:
        await get_repo(
            base_clone_path=str(tmp_path),
            clone_subdirectory_prefix="source",
            use_fixed_path=False,
            source_id=None,
        )

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_bundle_repository_lookup_uses_live_manifest_registry(
    monkeypatch, tmp_path
):
    source_path = tmp_path / "discovered-team-a"
    Repo.init(source_path)

    async def get_sources():
        return ApiPolicyBundleSources(
            sources=[
                {
                    "source_id": "team-a",
                    "url": "https://example.test/a",
                    "clone_path": str(source_path),
                }
            ]
        )

    monkeypatch.setattr(bundle_api, "get_active_policy_bundle_sources", get_sources)
    monkeypatch.setattr(
        opal_server_config,
        "POLICY_BUNDLE_MANIFEST_URL",
        "https://example.test/manifest.json",
    )

    repo = await get_repo(
        base_clone_path=str(tmp_path),
        clone_subdirectory_prefix="source",
        use_fixed_path=False,
        source_id="team-a",
    )

    assert Path(repo.working_tree_dir) == source_path


@pytest.mark.asyncio
async def test_webhook_topics_trigger_only_the_matching_source():
    class _Source:
        def __init__(self):
            self.trigger_count = 0

        async def check_for_changes(self):
            self.trigger_count += 1

    source_a = _Source()
    source_b = _Source()
    watcher = MultiPolicyWatcherTask(
        {"team-a": source_a, "team-b": source_b}, pubsub_endpoint=None
    )

    await watcher.trigger("webhook:team-a", None)

    assert source_a.trigger_count == 1
    assert source_b.trigger_count == 0


@pytest.mark.asyncio
async def test_manifest_webhook_publishes_source_id_on_stable_topic(monkeypatch):
    published = []

    async def get_sources():
        return ApiPolicyBundleSources(
            sources=[
                {"source_id": "team-a", "url": "https://example.test/a"},
                {"source_id": "team-b", "url": "https://example.test/b"},
            ]
        )

    async def publish(topics, data=None):
        published.append((topics, data))

    monkeypatch.setattr(webhook_api, "get_active_policy_bundle_sources", get_sources)
    monkeypatch.setattr(
        opal_server_config,
        "POLICY_BUNDLE_MANIFEST_URL",
        "https://example.test/manifest.json",
    )
    router = webhook_api.get_webhook_router([], None, PolicySourceTypes.Api, publish)
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/webhook",
            "raw_path": b"/webhook",
            "query_string": b"source_id=team-b",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        }
    )

    response = await router.routes[0].endpoint(request)

    assert response["source_id"] == "team-b"
    assert published == [
        (opal_server_config.POLICY_REPO_WEBHOOK_TOPIC, {"source_id": "team-b"})
    ]
