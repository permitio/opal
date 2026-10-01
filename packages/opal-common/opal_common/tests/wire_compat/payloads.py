"""The wire-compat corpus: inputs only, no pydantic.

This module is imported by BOTH sides of the comparison - a pydantic v1
interpreter running ``generate_golden.py`` against a pre-migration checkout,
and the pydantic v2 test suite - so it must stay free of any pydantic import
and of anything that differs between the two trees. Plain data only.

Every case pins each value that would otherwise be non-deterministic (uuids,
timestamps), because a golden file that changes run to run cannot be compared.

Add a case whenever a model reaches the wire: published to clients, served by
a route, persisted to Redis, or posted back by a client.
"""

from typing import Any, Dict, List, NamedTuple, Optional


class Case(NamedTuple):
    """One corpus entry.

    name      file-safe id; the golden file is ``golden/<name>.json``
    model     "module.path:ClassName", resolved by import in both trees
    payload   the dict fed to ``parse_obj`` (v1) / ``model_validate`` (v2)
    note      why this case is in the corpus - shown on failure
    builder   optional key into ``payload_builders.BUILDERS``. When set, the
              instance is CONSTRUCTED by that function rather than validated
              from ``payload``, which is the only way to exercise a subclass
              instance assigned to a parent-typed field - a dict can only ever
              validate into the declared type. ``payload`` is still recorded in
              the golden for reference.
    """

    name: str
    model: str
    payload: Dict[str, Any]
    note: str
    builder: Optional[str] = None


# --- building blocks ---------------------------------------------------------

_HTTP_CONFIG = {
    "fetcher": None,
    "headers": {"Authorization": "Bearer corpus-token", "X-Trace": "abc"},
    "is_json": True,
    "process_data": True,
    "method": "get",
    "data": None,
}

_ENTRY = {
    "url": "https://backend.example.com/v1/policy/data",
    "config": _HTTP_CONFIG,
    "topics": ["policy_data", "policy_data/tenant_1"],
    "dst_path": "/acl",
    "save_method": "PUT",
    "data": None,
}

_ENTRY_INLINE = {
    "url": "https://backend.example.com/v1/policy/data",
    "topics": ["policy_data"],
    "dst_path": "/acl",
    "save_method": "PUT",
    "data": {"users": {"alice": {"roles": ["admin"]}}, "count": 3},
}

_ENTRY_PATCH = {
    "url": "https://backend.example.com/v1/policy/data",
    "topics": ["policy_data"],
    "dst_path": "/acl",
    "save_method": "PATCH",
    "data": [
        {"op": "add", "path": "/users/bob", "value": {"roles": ["viewer"]}},
        {"op": "remove", "path": "/users/carol"},
    ],
}


CASES: List[Case] = [
    # --- the WebSocket publish payload: server -> every PDP in the field -----
    Case(
        "data_update_basic",
        "opal_common.schemas.data:DataUpdate",
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "entries": [_ENTRY],
            "reason": "corpus: basic fetch entry",
            "callback": {"callbacks": []},
        },
        "the primary publish payload; a v1 opal-client must parse whatever v2 emits",
    ),
    Case(
        "data_update_inline_data",
        "opal_common.schemas.data:DataUpdate",
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "entries": [_ENTRY_INLINE],
            "reason": "corpus: inline data payload",
            "callback": {"callbacks": []},
        },
        "inline data rides the JsonableValue union - trap 4 (smart vs left-to-right)",
    ),
    Case(
        "data_update_json_patch",
        "opal_common.schemas.data:DataUpdate",
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "entries": [_ENTRY_PATCH],
            "reason": "corpus: PATCH save_method",
            "callback": {"callbacks": []},
        },
        "the PATCH path: union order decides whether these stay JSONPatchAction",
    ),
    Case(
        "data_update_with_callbacks",
        "opal_common.schemas.data:DataUpdate",
        {
            "id": "44444444-4444-4444-4444-444444444444",
            "entries": [_ENTRY],
            "reason": "corpus: callbacks",
            "callback": {
                "callbacks": [
                    "https://callback.example.com/plain",
                    ["https://callback.example.com/configured", _HTTP_CONFIG],
                ]
            },
        },
        "UpdateCallback holds a Union[str, Tuple[str, HttpFetcherConfig]] - union mode",
    ),
    Case(
        "data_update_multi_entry",
        "opal_common.schemas.data:DataUpdate",
        {
            "id": "55555555-5555-5555-5555-555555555555",
            "entries": [_ENTRY, _ENTRY_INLINE, _ENTRY_PATCH],
            "reason": "corpus: mixed entries",
            "callback": {"callbacks": []},
        },
        "realistic multi-entry update",
    ),
    Case(
        "data_update_minimal",
        "opal_common.schemas.data:DataUpdate",
        {"entries": [{"url": "https://x.example.com/d"}]},
        "every optional field omitted - catches trap 1 (Optional becoming required)",
    ),
    # --- served to clients ---------------------------------------------------
    Case(
        "data_source_config",
        "opal_common.schemas.data:DataSourceConfig",
        {
            "entries": [
                dict(_ENTRY, periodic_update_interval=None),
                dict(_ENTRY_INLINE, periodic_update_interval=45.0),
            ]
        },
        "GET /data/config response; entries are the polling subclass",
    ),
    Case(
        "server_data_source_config_static",
        "opal_common.schemas.data:ServerDataSourceConfig",
        {"config": {"entries": [dict(_ENTRY, periodic_update_interval=None)]}},
        "the static server-side data source config",
    ),
    Case(
        "server_data_source_config_redirect",
        "opal_common.schemas.data:ServerDataSourceConfig",
        {"external_source_url": "https://backend.example.com/opal/data-sources"},
        "the redirect form - the other arm of the same model",
    ),
    Case(
        "policy_bundle_full",
        "opal_common.schemas.policy:PolicyBundle",
        {
            "manifest": ["acl.rego", "data.json"],
            "hash": "a" * 40,
            "old_hash": "b" * 40,
            "data_modules": [{"path": "tenants/tenant_1", "data": '{"x": 1}'}],
            "policy_modules": [
                {
                    "path": "acl.rego",
                    "package_name": "app.acl",
                    "rego": "package app.acl\n\ndefault allow = false\n",
                }
            ],
            "deleted_files": {
                "data_modules": ["tenants/tenant_9/data.json"],
                "policy_modules": ["old/policy.rego"],
            },
        },
        "GET /policy response; deleted_files holds List[Path] - Path serialization",
    ),
    Case(
        "policy_bundle_no_deleted",
        "opal_common.schemas.policy:PolicyBundle",
        {
            "manifest": ["acl.rego"],
            "hash": "c" * 40,
            "data_modules": [],
            "policy_modules": [],
        },
        "deleted_files omitted - the exact field trap 1 hit",
    ),
    Case(
        "policy_update_notification",
        "opal_common.schemas.policy:PolicyUpdateMessageNotification",
        {
            "update": {
                "old_policy_hash": "d" * 40,
                "new_policy_hash": "e" * 40,
                "changed_directories": ["/", "tenants"],
            },
            "topics": ["policy:default"],
        },
        "the policy-update publish payload",
    ),
    # --- client -> server ----------------------------------------------------
    Case(
        "data_update_report",
        "opal_common.schemas.data:DataUpdateReport",
        {
            "update_id": "66666666-6666-6666-6666-666666666666",
            "reports": [
                {"entry": _ENTRY, "fetched": True, "saved": True, "hash": "f" * 64},
                {"entry": _ENTRY_INLINE, "fetched": True, "saved": False},
            ],
            "policy_hash": "0" * 40,
            "user_data": {"pdp": "pdp-a-0"},
        },
        "POST /data/callback_report body, sent by a v1 client to a v2 server",
    ),
    # --- subclass instance in a parent-typed field ---------------------------
    # These are BUILT, not validated from a dict. A dict validates into the
    # declared type, so it cannot exercise the case where code assigns a
    # subclass - which is exactly how `periodic_update_interval` went missing
    # from every callback report under v2 until SerializeAsAny was added.
    Case(
        "data_update_report_subclass_entry",
        "opal_common.schemas.data:DataUpdateReport",
        {},
        "the callback report as CallbacksReporter actually builds it: a "
        "DataSourceEntryWithPollingInterval assigned to a DataSourceEntry field",
        builder="data_update_report_with_polling_entry",
    ),
    Case(
        "data_update_subclass_entry",
        "opal_common.schemas.data:DataUpdate",
        {},
        "the publish sibling: a polling entry assigned to DataUpdate.entries, "
        "which is declared List[DataSourceEntry]",
        builder="data_update_with_polling_entry",
    ),
    Case(
        "callback_entry",
        "opal_common.schemas.data:CallbackEntry",
        {
            "key": "cb-1",
            "url": "https://callback.example.com/hook",
            "config": _HTTP_CONFIG,
        },
        "POST /callbacks body; config is a declared HttpFetcherConfig",
    ),
    Case(
        "store_transaction_policy",
        "opal_common.schemas.store:StoreTransaction",
        {
            "id": "77777777-7777-7777-7777-777777777777",
            "actions": ["set_policies", "delete_policies"],
            "transaction_type": "policy",
            "success": True,
            "creation_time": "2026-09-15T10:00:00Z",
            "end_time": "2026-09-15T10:00:02Z",
            "remotes_status": [
                {"remote_url": "https://git.example.com/p.git", "succeed": True},
                {
                    "remote_url": "https://git.example.com/q.git",
                    "succeed": False,
                    "error": "GitError",
                },
            ],
        },
        "client-side transaction record; transaction_type is a str Enum",
    ),
    Case(
        "store_transaction_minimal",
        "opal_common.schemas.store:StoreTransaction",
        {"id": "88888888-8888-8888-8888-888888888888", "actions": []},
        "every optional omitted - transaction_type default must stay null",
    ),
    Case(
        "json_patch_action_with_from",
        "opal_common.schemas.store:JSONPatchAction",
        {"op": "move", "path": "/users/dave", "from": "/users/david"},
        "from_field carries alias='from' - populate-by-alias round trip",
    ),
    Case(
        "json_patch_action_add",
        "opal_common.schemas.store:JSONPatchAction",
        {"op": "add", "path": "/users/erin", "value": {"roles": []}},
        "the add branch of value_must_be_present (trap 3: ValueError not TypeError)",
    ),
    # --- auth ----------------------------------------------------------------
    Case(
        "access_token_request_default_ttl",
        "opal_common.schemas.security:AccessTokenRequest",
        {
            "id": "99999999-9999-9999-9999-999999999999",
            "type": "client",
            "claims": {"permit_client_id": "pdp-1"},
        },
        "the 365d default: v2 emitted P1Y, which a v1 server cannot parse",
    ),
    Case(
        "access_token_request_explicit_ttl",
        "opal_common.schemas.security:AccessTokenRequest",
        {
            "id": "aaaaaaaa-9999-9999-9999-999999999999",
            "type": "datasource",
            "ttl": 3600,
            "claims": {},
        },
        "explicit numeric ttl must round trip as a number",
    ),
    Case(
        "access_token",
        "opal_common.schemas.security:AccessToken",
        {
            "token": "eyJhbGciOiJSUzI1NiJ9.corpus.signature",
            "type": "bearer",
            "details": {
                "id": "bbbbbbbb-9999-9999-9999-999999999999",
                "type": "client",
                "expired": "2027-09-15T10:00:00+00:00",
                "claims": {"permit_client_id": "pdp-1"},
            },
        },
        "POST /token response; details is the Optional that trap 1 hit",
    ),
    Case(
        "access_token_naive_expiry",
        "opal_common.schemas.security:AccessToken",
        {
            "token": "eyJhbGciOiJSUzI1NiJ9.corpus.signature",
            "type": "bearer",
            "details": {
                "id": "dddddddd-9999-9999-9999-999999999999",
                "type": "client",
                # the production shape: security/api.py builds this with
                # datetime.utcnow() + ttl, which is NAIVE, not tz-aware
                "expired": "2027-09-15T10:00:00",
                "claims": {},
            },
        },
        "naive expiry, as POST /token actually emits it (datetime.utcnow())",
    ),
    Case(
        "access_token_no_details",
        "opal_common.schemas.security:AccessToken",
        {"token": "eyJhbGciOiJSUzI1NiJ9.corpus.signature"},
        "details omitted - must stay optional",
    ),
    # --- Redis persistence ---------------------------------------------------
    Case(
        "scope_ssh_auth",
        "opal_common.schemas.scopes:Scope",
        {
            "scope_id": "tenant-a",
            "policy": {
                "source_type": "git",
                "url": "git@github.com:acme/policy.git",
                "auth": {
                    "auth_type": "ssh",
                    "username": "git",
                    "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\\nCORPUS\\n",
                    "public_key": None,
                },
                "directories": ["."],
                "extensions": [".rego", ".json"],
                "manifest": ".manifest",
                "poll_updates": False,
                "branch": "main",
            },
            "data": {"entries": []},
        },
        "persisted to Redis by the server; v1-written records must read under v2",
    ),
    Case(
        "scope_token_auth",
        "opal_common.schemas.scopes:Scope",
        {
            "scope_id": "tenant-b",
            "policy": {
                "source_type": "git",
                "url": "https://github.com/acme/policy.git",
                "auth": {"auth_type": "github_token", "token": "ghp_corpus"},
                "directories": ["policies"],
                "extensions": [".rego"],
                "manifest": ".manifest",
                "poll_updates": True,
                "branch": "main",
            },
            "data": {"entries": [dict(_ENTRY, periodic_update_interval=None)]},
        },
        "the discriminated auth union, other arm, with a populated data config",
    ),
    Case(
        "scope_no_auth",
        "opal_common.schemas.scopes:Scope",
        {
            "scope_id": "tenant-c",
            "policy": {
                "source_type": "git",
                "url": "https://github.com/acme/public.git",
                "auth": {"auth_type": "none"},
                "directories": ["."],
                "extensions": [".rego"],
                "manifest": ".manifest",
                "poll_updates": False,
                "branch": "main",
            },
            "data": {"entries": []},
        },
        "no-auth arm; also the shape t3_contract case 3.8 probes",
    ),
    Case(
        "scope_userpass_auth",
        "opal_common.schemas.scopes:Scope",
        {
            "scope_id": "tenant-d",
            "policy": {
                "source_type": "git",
                "url": "https://git.example.com/acme/policy.git",
                "auth": {
                    "auth_type": "userpass",
                    "username": "ci-bot",
                    "password": "corpus-password",
                },
                "directories": ["."],
                "extensions": [".rego", ".json"],
                "manifest": ".manifest",
                "poll_updates": True,
                "branch": "main",
            },
            "data": {"entries": []},
        },
        "the fourth auth arm, and the only one carrying a credential in TWO "
        "fields; also extends the Redis round-trip driver, which enumerates "
        "these same cases",
    ),
    # --- client-served -------------------------------------------------------
    Case(
        "policy_store_details",
        "opal_client.policy_store.schemas:PolicyStoreDetails",
        {"url": "http://localhost:8181/v1", "type": "OPA", "auth_type": "token"},
        "GET /policy-store/config response_model. Two NON-str Enums under "
        "use_enum_values with a force_enum validator - the exact shape that "
        "produced the inline-OPA regression, so the wire form is pinned here",
    ),
    Case(
        "policy_store_details_defaults",
        "opal_client.policy_store.schemas:PolicyStoreDetails",
        {"url": "http://localhost:8181/v1"},
        "the same model with both enums left at their DEFAULTS - the path "
        "use_enum_values does not fire on under v2",
    ),
    # --- fetcher ------------------------------------------------------------
    Case(
        "http_fetcher_config",
        "opal_common.fetcher.providers.http_fetch_provider:HttpFetcherConfig",
        {"headers": {"Authorization": "Bearer corpus"}, "method": "post"},
        "method is a non-str Enum: v1 .dict() unwrapped it, v2 python-mode does not",
    ),
    Case(
        "http_fetch_event",
        "opal_common.fetcher.providers.http_fetch_provider:HttpFetchEvent",
        {
            "id": "cccccccc-9999-9999-9999-999999999999",
            "url": "https://backend.example.com/v1/data",
            "config": {"headers": {"Authorization": "Bearer corpus"}, "method": "get"},
        },
        "declared-model config; the coercion shim must leave this arm alone",
    ),
]


def case_by_name(name: str) -> Case:
    for case in CASES:
        if case.name == name:
            return case
    raise KeyError(name)
