"""Log sites in opal-server must redact auth.

Covers auth carried in URLs, client reports, git errors and RPC payloads.
Each test checks a text sink and a ``serialize=True`` sink: loguru keeps bound
kwargs in ``record["extra"]``, which the JSON sink prints verbatim. Both capture
with the patcher ``configure_logs`` installs disabled, so they see what the
call site itself emits.
"""

import logging
import re
from contextlib import contextmanager
from typing import Iterator, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi_websocket_rpc.logger import get_logger as get_rpc_library_logger
from opal_common.logging_utils.intercept import InterceptHandler
from opal_common.schemas.data import ServerDataSourceConfig
from opal_common.tests.redaction_fixtures import capture_logs
from opal_server import server as server_module
from opal_server.config import opal_server_config
from opal_server.data.api import init_data_updates_router
from opal_server.policy.watcher import task as watcher_task_module
from opal_server.redis_utils import RedisDB

FAKE_KEY = "FAKE-KEY-123"
FAKE_PASSWORD = "fakepass-FAKE-456"
FAKE_HEADER = "Bearer FAKE-KEY-789"


@contextmanager
def _captured_logs() -> Iterator[Tuple[List[str], List[str]]]:
    with capture_logs() as logs:
        yield logs.text, logs.serialized


def _assert_absent(values, *outputs: List[str]):
    for output in outputs:
        joined = "\n".join(output)
        for value in values:
            assert value not in joined, joined


class FakeAuthenticator:
    def __call__(self):
        return {}


# --- Redis URL (S3) ---------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_connect_log_masks_password():
    with _captured_logs() as (text, serialized):
        RedisDB(f"redis://fakeuser:{FAKE_PASSWORD}@redis.example.com:6379/0")

    assert any("Connecting to Redis" in line for line in text), text
    assert any(
        re.search(r"redis://\*\*\*@redis\.example\.com:6379", line)
        for line in serialized
    ), serialized
    _assert_absent([FAKE_PASSWORD], text, serialized)


# --- /data/config redirect log (L2) -----------------------------------------


def test_data_config_redirect_log_masks_external_source_url():
    external_url = f"https://fakeuser:{FAKE_PASSWORD}@config.example.com/sources?api_key={FAKE_KEY}"
    router = init_data_updates_router(
        None,
        ServerDataSourceConfig(external_source_url=external_url),
        FakeAuthenticator(),
    )
    app = FastAPI()
    app.include_router(router)

    with _captured_logs() as (text, serialized):
        response = TestClient(app).get(
            opal_server_config.DATA_CONFIG_ROUTE,
            headers={"Authorization": "Bearer fake.client.jwt-abcdefghij"},
            follow_redirects=False,
        )

    assert response.status_code == 307
    redirected = [
        line
        for line in serialized
        if re.search(r"https://\*\*\*@config\.example\.com/sources", line)
    ]
    assert redirected, serialized
    _assert_absent([FAKE_PASSWORD, FAKE_KEY], text, serialized)


# --- default update-callback report log (L3) --------------------------------


def test_default_callback_report_log_masks_entry_url_and_config():
    router = init_data_updates_router(
        None, ServerDataSourceConfig(config={"entries": []}), FakeAuthenticator()
    )
    app = FastAPI()
    app.include_router(router)
    report = {
        "update_id": "fake-update",
        "reports": [
            {
                "entry": {
                    "url": f"https://fakeuser:{FAKE_PASSWORD}@data.example.com/v1?token={FAKE_KEY}",
                    "config": {"headers": {"Authorization": FAKE_HEADER}},
                    "topics": ["policy_data"],
                },
                "fetched": True,
                "saved": True,
            }
        ],
    }

    with _captured_logs() as (text, serialized):
        response = TestClient(app).post(
            opal_server_config.DATA_CALLBACK_DEFAULT_ROUTE, json=report
        )

    assert response.status_code == 200
    received = [line for line in serialized if "Received update report" in line]
    assert received and "data.example.com/v1" in received[0], serialized
    _assert_absent([FAKE_PASSWORD, FAKE_KEY, FAKE_HEADER], text, serialized)


# --- policy watcher failure log (L8) ----------------------------------------


@pytest.mark.asyncio
async def test_policy_watcher_failure_log_masks_remote_auth(monkeypatch):
    monkeypatch.setattr(watcher_task_module.os, "kill", lambda pid, sig: None)
    watcher = watcher_task_module.BasePolicyWatcherTask(pubsub_endpoint=None)
    error = RuntimeError(
        f"fetch failed for https://fakeuser:{FAKE_PASSWORD}@git.example.com/org/policy.git"
    )

    with _captured_logs() as (text, serialized):
        await watcher._fail(error)

    failed = [line for line in serialized if "policy watcher failed" in line]
    assert failed and "git.example.com/org/policy.git" in failed[0], serialized
    _assert_absent([FAKE_PASSWORD], text, serialized)


# --- RPC library DEBUG logs (M1) --------------------------------------------


@pytest.fixture
def stdlib_logs_to_loguru():
    """Route stdlib logging into loguru the way configure_logs() does (root
    handler = InterceptHandler, root level 0), and restore everything after."""
    root = logging.getLogger()
    rpc_logger = logging.getLogger(server_module.RPC_LIBRARY_LOGGER_NAME)
    saved_root_level = root.level
    saved_rpc_level = rpc_logger.level
    handler = InterceptHandler()
    root.addHandler(handler)
    root.setLevel(logging.NOTSET)
    rpc_logger.setLevel(logging.NOTSET)
    try:
        yield
    finally:
        root.removeHandler(handler)
        root.setLevel(saved_root_level)
        rpc_logger.setLevel(saved_rpc_level)


def _emit_rpc_library_records():
    """One DEBUG record shaped like RpcChannel's request log (payload included)
    and one INFO lifecycle record, both from the libraries' own loggers."""
    channel_logger = get_rpc_library_logger("RPC_CHANNEL")
    pubsub_logger = get_rpc_library_logger("pubsub.EventNotifier")
    channel_logger.debug(
        "Handling RPC request - %s",
        {"request": {"headers": {"Authorization": FAKE_HEADER}}},
    )
    pubsub_logger.debug("notify %s", {"Authorization": FAKE_HEADER})
    channel_logger.info("Client connected")


def test_no_rpc_logs_drops_library_debug_records(monkeypatch, stdlib_logs_to_loguru):
    monkeypatch.setattr(opal_server_config, "NO_RPC_LOGS", True)
    server_module.configure_rpc_library_logs()

    with _captured_logs() as (text, serialized):
        _emit_rpc_library_records()

    assert any("Client connected" in line for line in text), text
    # Checked on the record text as well as the header value: the records must
    # be dropped, not just masked.
    assert not any("Handling RPC request" in line for line in text), text
    assert not any("notify" in line for line in text), text
    _assert_absent([FAKE_HEADER], text, serialized)


def test_rpc_library_debug_records_flow_when_no_rpc_logs_is_off(
    monkeypatch, stdlib_logs_to_loguru
):
    """The inverse, so the test above cannot pass because the records never
    reach loguru in the first place."""
    monkeypatch.setattr(opal_server_config, "NO_RPC_LOGS", False)
    server_module.configure_rpc_library_logs()

    with _captured_logs() as (text, _serialized):
        _emit_rpc_library_records()

    assert any("Handling RPC request" in line for line in text), text
    assert any("notify" in line for line in text), text
