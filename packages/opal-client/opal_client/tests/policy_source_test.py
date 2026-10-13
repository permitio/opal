import pytest
from opal_client.policy import fetcher as fetcher_module
from opal_client.policy import updater as updater_module
from opal_client.policy.fetcher import PolicyFetcher
from opal_client.policy.topics import resolve_policy_source_ids
from opal_client.policy.updater import PolicyUpdater, merge_source_policy_bundles
from opal_common.schemas.policy import DataModule, PolicyBundle, RegoModule


class _Response:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self):
        return {
            "manifest": [],
            "hash": "team-b-hash",
            "data_modules": [],
            "policy_modules": [],
        }


class _Session:
    def __init__(self, requested):
        self.requested = requested

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def get(self, url, headers, params, **kwargs):
        self.requested.update(url=url, params=params)
        return _Response()


def test_resolve_policy_source_ids_keeps_single_source_compatibility():
    assert resolve_policy_source_ids("team-a", []) == ["team-a"]
    assert resolve_policy_source_ids(None, ["team-a", "team-b"]) == [
        "team-a",
        "team-b",
    ]


@pytest.mark.parametrize(
    "single_source_id, source_ids",
    [
        ("team-a", ["team-b"]),
        (None, ["team-a", "team-a"]),
        (None, ["team-a", ""]),
        (None, ["team:a"]),
    ],
)
def test_resolve_policy_source_ids_rejects_ambiguous_or_invalid_lists(
    single_source_id, source_ids
):
    with pytest.raises(ValueError):
        resolve_policy_source_ids(single_source_id, source_ids)


@pytest.mark.asyncio
async def test_policy_fetcher_scopes_requests_to_configured_source(monkeypatch):
    requested = {}

    monkeypatch.setattr(
        fetcher_module.aiohttp,
        "ClientSession",
        lambda **kwargs: _Session(requested),
    )

    async def accept_status(response, expected, logger):
        return None

    monkeypatch.setattr(fetcher_module, "throw_if_bad_status_code", accept_status)
    fetcher = PolicyFetcher(
        backend_url="http://opal-server",
        token="token",
        source_id="team-a",
    )

    bundle = await fetcher._fetch_policy_bundle(
        ["."], base_hash="old-hash", source_id="team-b"
    )

    assert requested["url"] == "http://opal-server/policy"
    assert requested["params"] == {
        "path": ["."],
        "base_hash": "old-hash",
        "source_id": "team-b",
    }
    assert bundle.hash == "team-b-hash"


@pytest.mark.asyncio
async def test_policy_updater_ignores_updates_for_other_sources():
    updater = object.__new__(PolicyUpdater)
    updater._source_ids = ["team-a"]
    updater._subscription_directories = ["."]
    triggered = []

    async def record_update(directories, force_full_update=False, source_id=None):
        triggered.append((directories, source_id))

    updater.trigger_update_policy = record_update

    await updater._update_policy_callback(
        data={
            "old_policy_hash": "old",
            "new_policy_hash": "new",
            "changed_directories": ["."],
            "source_id": "team-b",
        },
        topic="policy:team-b:.",
    )

    assert triggered == []


@pytest.mark.asyncio
async def test_policy_updater_queues_selected_source_events():
    updater = object.__new__(PolicyUpdater)
    updater._source_ids = ["team-a", "team-b"]
    updater._subscription_directories = ["."]
    triggered = []

    async def record_update(directories, force_full_update=False, source_id=None):
        triggered.append((directories, source_id))

    updater.trigger_update_policy = record_update

    await updater._update_policy_callback(
        data={
            "old_policy_hash": "old",
            "new_policy_hash": "new",
            "changed_directories": ["."],
            "source_id": "team-b",
        },
        topic="policy:team-b:.",
    )

    assert triggered == [(["."], "team-b")]


def _bundle(source_hash, modules=(), data_modules=()):
    return PolicyBundle(
        manifest=[module.path for module in modules],
        hash=source_hash,
        data_modules=list(data_modules),
        policy_modules=list(modules),
    )


def test_merge_source_bundles_retains_modules_from_all_streams():
    aggregate = merge_source_policy_bundles(
        {
            "team-a": _bundle(
                "hash-a",
                [RegoModule(path="a.rego", package_name="a", rego="package a")],
            ),
            "team-b": _bundle(
                "hash-b",
                [RegoModule(path="b.rego", package_name="b", rego="package b")],
            ),
        }
    )

    assert {module.path for module in aggregate.policy_modules} == {
        "a.rego",
        "b.rego",
    }
    assert aggregate.old_hash is None
    assert len(aggregate.hash) == 64


def test_merge_source_bundles_allows_shared_package_within_one_stream():
    aggregate = merge_source_policy_bundles(
        {
            "team-a": _bundle(
                "hash-a",
                [
                    RegoModule(path="a.rego", package_name="a", rego="package a"),
                    RegoModule(path="a_extra.rego", package_name="a", rego="package a"),
                ],
            ),
            "team-b": _bundle(
                "hash-b",
                [RegoModule(path="b.rego", package_name="b", rego="package b")],
            ),
        }
    )

    assert len(aggregate.policy_modules) == 3


@pytest.mark.asyncio
async def test_source_update_removal_does_not_delete_another_stream(monkeypatch):
    class _Store:
        def __init__(self):
            self.bundle = None

        def transaction_context(self, transaction_id, transaction_type):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def _update_remote_status(self, **kwargs):
            pass

        async def set_policies(self, bundle):
            self.bundle = bundle

    class _Fetcher:
        policy_endpoint_url = "http://opal-server/policy"

        def __init__(self):
            self.calls = []

        async def fetch_policy_bundle(self, directories, base_hash, source_id):
            self.calls.append((directories, source_id, base_hash))
            return _bundle(
                "new-a-hash",
                [RegoModule(path="a-new.rego", package_name="a", rego="package a")],
            )

    updater = object.__new__(PolicyUpdater)
    updater._subscription_directories = ["policy-a", "policy-b"]
    updater._source_ids = ["team-a", "team-b"]
    updater._source_bundles = {
        "team-a": _bundle(
            "old-a-hash",
            [RegoModule(path="a-old.rego", package_name="a", rego="package a")],
        ),
        "team-b": _bundle(
            "b-hash",
            [RegoModule(path="b.rego", package_name="b", rego="package b")],
        ),
    }
    updater._source_hashes = {"team-a": "old-a-hash", "team-b": "b-hash"}
    updater._policy_fetcher = _Fetcher()
    updater._policy_store = _Store()
    updater._should_send_reports = False

    monkeypatch.setattr(
        updater_module,
        "default_subscribed_policy_directories",
        lambda directories: ["policy-a", "policy-b"],
    )

    await updater._update_multiple_source_policies(
        directories=["policy-a/changed"],
        force_full_update=False,
        source_id="team-a",
    )

    assert updater._policy_fetcher.calls == [(["policy-a", "policy-b"], "team-a", None)]
    assert {module.path for module in updater._policy_store.bundle.policy_modules} == {
        "a-new.rego",
        "b.rego",
    }
    assert updater._source_hashes == {"team-a": "new-a-hash", "team-b": "b-hash"}


@pytest.mark.parametrize(
    "first, second, message",
    [
        (
            _bundle("a", [RegoModule(path="shared.rego", package_name="a", rego="")]),
            _bundle("b", [RegoModule(path="shared.rego", package_name="b", rego="")]),
            "module path",
        ),
        (
            _bundle("a", [RegoModule(path="a.rego", package_name="shared", rego="")]),
            _bundle("b", [RegoModule(path="b.rego", package_name="shared", rego="")]),
            "Rego package",
        ),
        (
            _bundle("a", data_modules=[DataModule(path="/users", data="{}")]),
            _bundle("b", data_modules=[DataModule(path="/users/admin", data="{}")]),
            "overlap",
        ),
    ],
)
def test_merge_source_bundles_rejects_cross_stream_collisions(first, second, message):
    with pytest.raises(ValueError, match=message):
        merge_source_policy_bundles({"team-a": first, "team-b": second})
