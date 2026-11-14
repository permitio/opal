"""A request for the policy or data of a scope that is not stored.

OPAL_SCOPES_MISSING_SCOPE=default (the default) answers as before: the
default scope's policy, and an empty data config (or the redirect to
OPAL_DATA_CONFIG_SOURCES's external source). not_found answers 404 for
both, so a client whose scope record is gone keeps the policy and data
it has instead of switching to the default scope's. Either way the
request logs a WARNING and counts opal_server.scopes.missing_scope.
"""

import pygit2
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opal_common.monitoring import metrics
from opal_common.schemas.data import ServerDataSourceConfig
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_common.tests.redaction_fixtures import capture_logs
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher
from opal_server.scopes import task as task_module
from opal_server.scopes.api import init_scope_router
from opal_server.scopes.missing_scope import validate_missing_scope_settings
from opal_server.scopes.scope_repository import ScopeNotFoundError
from opal_server.server import OpalServer

# The default scope's bundle comes from a real clone, made by either backend.
pytestmark = pytest.mark.fetch_backend("both")

_METRIC = "opal_server.scopes.missing_scope"


class _Scopes:
    def __init__(self, scopes=()):
        self.scopes = {s.scope_id: s for s in scopes}

    async def get(self, scope_id):
        if scope_id not in self.scopes:
            raise ScopeNotFoundError(scope_id)
        return self.scopes[scope_id]


class _Authenticator:
    enabled = False

    def __call__(self):
        return {}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    for name in ("repos", "repos_last_fetched", "repo_locks", "source_backoff"):
        monkeypatch.setattr(GitPolicyFetcher, name, {})
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path / "base"))
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_URL", None)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN", None)
    # The global data sources, which a missing scope's clients never get.
    monkeypatch.setattr(
        opal_server_config,
        "DATA_CONFIG_SOURCES",
        ServerDataSourceConfig(
            config={
                "entries": [
                    {"url": "http://global.example.test", "topics": ["policy_data"]}
                ]
            }
        ),
    )


@pytest.fixture
def counted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        metrics, "increment", lambda metric, tags=None: calls.append((metric, tags))
    )
    monkeypatch.setattr(metrics, "gauge", lambda *a, **k: None)
    monkeypatch.setattr(metrics, "event", lambda *a, **k: None)
    return calls


def _missing(counted):
    return [tags for metric, tags in counted if metric == _METRIC]


def _source(url: str) -> GitPolicyScopeSource:
    return GitPolicyScopeSource(
        source_type="git", url=url, branch="main", auth=NoAuthData()
    )


async def _default_scope(tmp_path) -> "tuple[Scope, str]":
    """The default scope, whose clone of a local origin has landed, and the
    origin's head."""
    origin = pygit2.init_repository(str(tmp_path / "origin"), bare=True)
    signature = pygit2.Signature("opal-test", "opal-test@example.com")
    builder = origin.TreeBuilder()
    builder.insert(
        "policy.rego",
        origin.create_blob(b"package default_scope\n"),
        pygit2.enums.FileMode.BLOB,
    )
    head = str(
        origin.create_commit(
            "refs/heads/main", signature, signature, "main", builder.write(), []
        )
    )
    origin.set_head("refs/heads/main")
    scope = Scope(scope_id="default", policy=_source(str(tmp_path / "origin")))
    fetcher = GitPolicyFetcher(tmp_path / "base", "default", scope.policy)
    await fetcher.fetch_and_notify_on_changes()
    return scope, head


def _client(scopes) -> AsyncClient:
    app = FastAPI()
    app.include_router(
        init_scope_router(scopes, _Authenticator(), None, None), prefix="/scopes"
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://opal")


@pytest.mark.asyncio
async def test_by_default_a_missing_scope_gets_the_default_scope_s_policy(
    tmp_path, monkeypatch, counted
):
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "default")
    default, head = await _default_scope(tmp_path)

    async with _client(_Scopes([default])) as client:
        response = await client.get("/scopes/ghost/policy")

    assert response.status_code == 200
    assert response.json()["hash"] == head
    assert _missing(counted) == [{"route": "policy"}]


@pytest.mark.asyncio
async def test_not_found_never_serves_the_default_scope_s_policy(
    tmp_path, monkeypatch, counted
):
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "not_found")
    default, _ = await _default_scope(tmp_path)

    async with _client(_Scopes([default])) as client:
        response = await client.get("/scopes/ghost/policy")
        served = await client.get("/scopes/default/policy")

    assert response.status_code == 404
    assert response.json() == {"detail": "No such scope: ghost"}
    assert served.status_code == 200
    assert _missing(counted) == [{"route": "policy"}]


@pytest.mark.asyncio
async def test_by_default_with_no_default_scope_a_missing_scope_is_a_404(
    monkeypatch, counted
):
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "default")

    async with _client(_Scopes()) as client:
        response = await client.get("/scopes/ghost/policy")

    assert response.status_code == 404
    assert _missing(counted) == [{"route": "policy"}]


@pytest.mark.parametrize(
    "mode, status, body",
    [
        ("default", 200, {"entries": []}),
        ("not_found", 404, {"detail": "No such scope: ghost"}),
    ],
    ids=["default", "not_found"],
)
@pytest.mark.asyncio
async def test_a_missing_scope_s_data_config(monkeypatch, counted, mode, status, body):
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", mode)

    async with _client(_Scopes()) as client:
        response = await client.get("/scopes/ghost/data")

    assert response.status_code == status
    assert response.json() == body
    assert _missing(counted) == [{"route": "data"}]


@pytest.mark.parametrize(
    "mode, status", [("default", 307), ("not_found", 404)], ids=["default", "not_found"]
)
@pytest.mark.asyncio
async def test_a_missing_scope_s_data_with_an_external_data_config_source(
    monkeypatch, counted, mode, status
):
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", mode)
    monkeypatch.setattr(
        opal_server_config,
        "DATA_CONFIG_SOURCES",
        ServerDataSourceConfig(external_source_url="http://backend.example.test/data"),
    )

    async with _client(_Scopes()) as client:
        response = await client.get("/scopes/ghost/data")

    assert response.status_code == status
    if status == 307:
        assert response.headers["location"].startswith("http://backend.example.test/")
    assert _missing(counted) == [{"route": "data"}]


@pytest.mark.parametrize("mode", ["default", "not_found"])
@pytest.mark.parametrize(
    "route, says",
    [
        (
            "policy",
            {"default": "returning default scope", "not_found": "returning 404"},
        ),
        (
            "data",
            {
                "default": "serving an empty data config",
                "not_found": "returning 404",
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_each_request_for_a_missing_scope_logs_a_warning(
    monkeypatch, counted, mode, route, says
):
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", mode)

    with capture_logs() as logs:
        async with _client(_Scopes()) as client:
            await client.get(f"/scopes/ghost/{route}")
            await client.get(f"/scopes/ghost/{route}")

    warnings = [
        line
        for line in logs.text
        if "WARNING" in line and "Requested scope ghost not found" in line
    ]
    assert len(warnings) == 2
    assert all(says[mode] in line for line in warnings)
    assert len(_missing(counted)) == 2


@pytest.mark.asyncio
async def test_a_stored_scope_counts_nothing(tmp_path, monkeypatch, counted):
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "not_found")
    default, _ = await _default_scope(tmp_path)

    async with _client(_Scopes([default])) as client:
        assert (await client.get("/scopes/default/policy")).status_code == 200
        assert (await client.get("/scopes/default/data")).status_code == 200

    assert _missing(counted) == []


# --- the settings, at start ----------------------------------------------------


@pytest.mark.parametrize("mode", ["", "NOT_FOUND", "404", "none"])
def test_a_mode_that_is_neither_stops_a_scopes_server(monkeypatch, mode):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", mode)

    with pytest.raises(
        ValueError, match="OPAL_SCOPES_MISSING_SCOPE.*default or not_found"
    ):
        validate_missing_scope_settings()


@pytest.mark.parametrize(
    "url",
    [
        "ftp://user:hunter2@backend.example.test/hooks/hunter2",
        "backend.example.test/missing?token=hunter2",
        "https:///missing?token=hunter2",
        "http://[::1/missing?token=hunter2",
        "http://backend.example.test:99999/missing?token=hunter2",
    ],
    ids=["ftp", "no-scheme", "no-host", "unparsable", "port-out-of-range"],
)
def test_a_webhook_url_that_is_not_http_stops_a_scopes_server(monkeypatch, url):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "default")
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_URL", url)

    with pytest.raises(ValueError, match="OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_URL") as e:
        validate_missing_scope_settings()

    assert "hunter2" not in str(e.value)


def test_a_webhook_url_with_a_password_and_a_token_stops_a_scopes_server(monkeypatch):
    """The POST can carry one of them, not both."""
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "default")
    monkeypatch.setattr(
        opal_server_config,
        "SCOPES_MISSING_SCOPE_WEBHOOK_URL",
        "https://opal:url-password@backend.example.test/hooks/url-password",
    )
    monkeypatch.setattr(
        opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN", "hunter2"
    )

    with pytest.raises(
        ValueError, match="OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN"
    ) as e:
        validate_missing_scope_settings()

    assert "hunter2" not in str(e.value) and "url-password" not in str(e.value)


def test_a_webhook_token_without_a_url_stops_a_scopes_server(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "default")
    monkeypatch.setattr(
        opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN", "hunter2"
    )

    with pytest.raises(ValueError, match="OPAL_SCOPES_MISSING_SCOPE_WEBHOOK_URL") as e:
        validate_missing_scope_settings()

    assert "hunter2" not in str(e.value)


@pytest.mark.parametrize(
    "url, token",
    [
        ("https://backend.example.test/missing", "hunter2"),
        ("http://127.0.0.1:8000/missing", None),
        (None, None),
        ("", None),
    ],
    ids=["https-with-token", "http-without-token", "unset", "empty"],
)
def test_settings_a_scopes_server_takes(monkeypatch, url, token):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "not_found")
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_URL", url)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE_WEBHOOK_TOKEN", token)

    validate_missing_scope_settings()


def test_the_settings_are_not_checked_with_scopes_off(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "bogus")

    validate_missing_scope_settings()


def test_the_server_refuses_to_start_on_a_bad_mode(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "bogus")

    with pytest.raises(ValueError, match="OPAL_SCOPES_MISSING_SCOPE"):
        OpalServer(
            init_policy_watcher=False, broadcaster_uri=None, enable_jwks_endpoint=False
        )


def test_the_preload_refuses_a_bad_mode_before_any_clone(
    monkeypatch, preload_sandbox, no_redis
):
    synced = []

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            synced.append(1)

    monkeypatch.setattr(task_module, "ScopesService", _Service)
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_MISSING_SCOPE", "bogus")

    with pytest.raises(ValueError, match="OPAL_SCOPES_MISSING_SCOPE"):
        task_module.ScopesPolicyWatcherTask.preload_scopes()

    assert synced == []
