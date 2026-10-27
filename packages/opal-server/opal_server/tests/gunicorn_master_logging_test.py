"""The gunicorn master must configure logging before it logs anything.

``scripts/gunicorn_conf.py::when_ready`` runs in the gunicorn master, where no
worker has called ``configure_logs()``. Anything logged before that call goes
to loguru's default handler: DEBUG level, plaintext, no credential scrubbing.

These tests run the real ``configure_logs()`` against a loguru whose only sink
is a recording stand-in for that default handler. ``configure_logs()`` removes
the stand-in, so whatever it recorded reached the default handler before
logging was configured.
"""

import asyncio
import contextlib
import importlib.abc
import importlib.util
import io
import json
import logging
import sys
import threading
from pathlib import Path

import opal_common.logger as opal_logger
import opal_server.scopes
import opal_server.scopes.task as task_module
import pytest
from loguru import logger
from opal_common.config import opal_common_config
from opal_common.http_utils import redact_url
from opal_common.logger import configure_logs
from opal_server.config import opal_server_config
from uvicorn.config import LOGGING_CONFIG

GUNICORN_CONF = Path(__file__).resolve().parents[4] / "scripts" / "gunicorn_conf.py"
CREDENTIAL = "s3cret-FAKE-123"
CREDENTIALED_REMOTE = f"https://user:{CREDENTIAL}@git.example.com/org/policy.git"
CREDENTIALED_REDIS_URL = f"redis://:{CREDENTIAL}@redis.example.com:6379"
CLONE_ERROR = repr(Exception(f"clone failed for {CREDENTIALED_REMOTE}"))
# The stdlib loggers configure_logs() rewires: hijack_uvicorn_logs takes the
# uvicorn names from the same LOGGING_CONFIG, fix_ddtrace_logging the other.
STDLIB_LOGGERS_CONFIGURE_LOGS_TOUCHES = (*LOGGING_CONFIG["loggers"], "ddtrace")


class MasterLogs:
    def __init__(self):
        #: when_ready and the stubbed preload run on this thread. Worker threads
        #: earlier tests left behind can log at any moment (e.g. a late Future
        #: callback error), which a real master, a fresh process, never sees.
        self.thread_id = threading.get_ident()
        #: (level, message) of every record the default-handler stand-in got.
        self.default_records = []
        #: What the configured sink wrote (the stream configure_logs() bound).
        self.stream = io.StringIO()

    @contextlib.contextmanager
    def streams(self):
        """configure_logs() binds sys.stderr/stdout when it runs; pytest swaps
        them per test phase, so redirect only around the configuring call."""
        with contextlib.redirect_stderr(self.stream), contextlib.redirect_stdout(
            self.stream
        ):
            yield

    def configured(self):
        """(level, message) of every record the configured sink wrote from this
        test's thread."""
        records = [
            json.loads(line)["record"]
            for line in self.stream.getvalue().splitlines()
            if line.startswith("{")
        ]
        return [
            (r["level"]["name"], r["message"])
            for r in records
            if r["thread"]["id"] == self.thread_id
        ]


def _is_pytest_handler(handler):
    return type(handler).__module__.startswith("_pytest")


@pytest.fixture
def master_logs(monkeypatch):
    """A fresh process's loguru state; prior state is restored afterwards.

    loguru's ``Core`` starts with no handlers, no patcher and
    ``min_level=inf``; the stand-in then plays the default stderr handler.
    Handlers are swapped out by assignment, never ``logger.remove()``, which
    would stop the ones restored at teardown. Teardown also restores the
    non-pytest root handlers and the stdlib loggers configure_logs() rewires.
    pytest's root handlers are not restored: ``basicConfig(force=True)``
    closes them, as building an OpalServer does. pytest re-adds its per-phase
    capture handlers; its live-log and log-file handlers stay detached for
    the rest of the session.
    """
    # Before any state is swapped, so a failure here leaves nothing to undo.
    monkeypatch.setattr(opal_common_config, "LOG_LEVEL", "INFO")
    monkeypatch.setattr(opal_common_config, "LOG_SERIALIZE", True)
    monkeypatch.setattr(opal_common_config, "LOG_COLORIZE", False)
    monkeypatch.setattr(opal_common_config, "LOG_TO_FILE", False)
    monkeypatch.setattr(opal_common_config, "LOG_PIPE_TO_STDERR", True)
    monkeypatch.setattr(opal_logger, "_logs_configured", False)
    core = logger._core
    # Private loguru state (as in redaction_fixtures.without_log_patcher):
    # fail loudly if a loguru upgrade renames it, rather than swap nothing.
    assert isinstance(core.handlers, dict), "loguru internals changed"
    saved_core = (core.handlers, core.min_level, core.patcher)
    root = logging.getLogger()
    saved_root_handlers = [h for h in root.handlers if not _is_pytest_handler(h)]
    saved_root_level = root.level
    saved_stdlib = {}
    for name in STDLIB_LOGGERS_CONFIGURE_LOGS_TOUCHES:
        lg = logging.getLogger(name)
        saved_stdlib[name] = (list(lg.handlers), lg.propagate, lg.level)

    try:
        core.handlers, core.min_level, core.patcher = {}, float("inf"), None
        # A fresh process's root logger: no handlers of ours, level WARNING (an
        # InterceptHandler an earlier test left would route stdlib on its own).
        for handler in saved_root_handlers:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)
        logs = MasterLogs()
        logger.add(
            lambda m: logs.default_records.append(
                (m.record["level"].name, m.record["message"])
            ),
            level="DEBUG",
            filter=lambda r: r["thread"].id == logs.thread_id,
        )
        yield logs
    finally:
        logger.remove()
        core.handlers, core.min_level, core.patcher = saved_core

        root.handlers = [h for h in root.handlers if _is_pytest_handler(h)]
        root.handlers += saved_root_handlers
        root.setLevel(saved_root_level)

        for name, (handlers, propagate, level) in saved_stdlib.items():
            lg = logging.getLogger(name)
            lg.handlers, lg.propagate = handlers, propagate
            lg.setLevel(level)


@pytest.fixture
def gunicorn_conf():
    """Loads scripts/gunicorn_conf.py (not a package) the way gunicorn's -c
    does."""
    spec = importlib.util.spec_from_file_location("gunicorn_conf", GUNICORN_CONF)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeScopesService:
    def __init__(self, *args, **kwargs):
        pass

    async def sync_scopes(self, *args, **kwargs):
        # Stands in for the per-scope git chatter of the real preload; the
        # error has the level and shape of GitPolicyFetcher._clone's failure
        # line, whose err kwarg (raw, as git renders it) also lands in
        # record["extra"].
        logger.debug("fake sync detail")
        logger.info("fake sync info")
        logger.error(
            "Could not clone repo at {url}: {err}",
            url=redact_url(CREDENTIALED_REMOTE),
            err=CLONE_ERROR,
        )


def _fake_redis_db(url):
    # Logs its URL on construction, as opal_server.redis_utils.RedisDB does. The
    # fake passes it raw, so only the master's own log setup can mask it.
    logger.debug("Connecting to Redis: {url}", url=url)
    return object()


@pytest.fixture
def stub_preload(monkeypatch):
    monkeypatch.setattr(opal_server_config, "REDIS_URL", CREDENTIALED_REDIS_URL)
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)
    monkeypatch.setattr(task_module, "RedisDB", _fake_redis_db)
    monkeypatch.setattr(task_module, "ScopeRepository", lambda db: object())
    monkeypatch.setattr(task_module, "ScopesService", _FakeScopesService)
    monkeypatch.setattr(task_module, "drain_git_ops", lambda timeout: True)
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(
        task_module.GitPolicyFetcher, "reset_caches", staticmethod(lambda: None)
    )
    yield
    # preload_scopes' asyncio.run() leaves the main thread without a current
    # loop; give it one back for later tests (same as the preload_*_test.py
    # files).
    asyncio.set_event_loop(asyncio.new_event_loop())


def _run_when_ready(gunicorn_conf, master_logs, monkeypatch, scopes):
    monkeypatch.setattr(opal_server_config, "SCOPES", scopes)
    with master_logs.streams():
        gunicorn_conf.when_ready(None)


@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
def test_when_ready_scopes_on_no_record_reaches_default_handler(
    level, master_logs, gunicorn_conf, stub_preload, monkeypatch, tmp_path
):
    monkeypatch.setattr(opal_common_config, "LOG_LEVEL", level)
    # The file sink is path-based, so it isn't stream-wrapped: only the
    # patcher keeps credentials out of it, message and extra alike.
    log_file = tmp_path / "opal.log"
    monkeypatch.setattr(opal_common_config, "LOG_TO_FILE", True)
    monkeypatch.setattr(opal_common_config, "LOG_FILE_PATH", str(log_file))

    _run_when_ready(gunicorn_conf, master_logs, monkeypatch, scopes=True)

    assert master_logs.default_records == []
    configured = master_logs.configured()
    assert ("INFO", "Preloading repo clones for scopes") in configured
    assert ("INFO", "fake sync info") in configured
    assert ("WARNING", "Finished preloading repo clones for scopes.") in configured
    assert ("WARNING", "Finished pre loading scopes...") in configured
    # No credential reaches the master's output: the git remote line is masked,
    # and the Redis URL line (DEBUG) is checked masked in the DEBUG case below.
    assert any("git.example.com/org/policy.git" in m for _, m in configured)
    assert CREDENTIAL not in master_logs.stream.getvalue()
    file_output = log_file.read_text()
    assert "Could not clone repo at" in file_output
    assert CREDENTIAL not in file_output
    debug = [m for lvl, m in configured if lvl == "DEBUG"]
    if level == "INFO":
        assert debug == []
    else:
        assert "fake sync detail" in debug
        assert "Connecting to Redis: redis://***@redis.example.com:6379" in debug


def test_when_ready_scopes_off_warning_goes_to_configured_handler(
    master_logs, gunicorn_conf, stub_preload, monkeypatch
):
    _run_when_ready(gunicorn_conf, master_logs, monkeypatch, scopes=False)

    assert master_logs.default_records == []
    assert master_logs.configured() == [("WARNING", "Finished pre loading scopes...")]


@pytest.mark.parametrize("scopes", [True, False])
def test_default_handler_sees_records_when_configure_logs_is_skipped(
    scopes, master_logs, gunicorn_conf, stub_preload, monkeypatch
):
    """Positive control: the stand-in does record what reaches the default
    handler, so the empty assertions above mean something. preload_scopes'
    own fallback is skipped too, as in a master where nothing configures."""
    monkeypatch.setattr(gunicorn_conf, "configure_logs", lambda: None)
    monkeypatch.setattr(task_module, "configure_logs", lambda: None)

    _run_when_ready(gunicorn_conf, master_logs, monkeypatch, scopes=scopes)

    assert ("WARNING", "Finished pre loading scopes...") in master_logs.default_records
    if scopes:
        assert ("DEBUG", "fake sync detail") in master_logs.default_records
        clone_line = (
            f"Could not clone repo at {redact_url(CREDENTIALED_REMOTE)}: {CLONE_ERROR}"
        )
        assert ("ERROR", clone_line) in master_logs.default_records
        redis_line = f"Connecting to Redis: {CREDENTIALED_REDIS_URL}"
        assert ("DEBUG", redis_line) in master_logs.default_records
    assert master_logs.stream.getvalue() == ""


class _FakeScopesTaskModule(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Serves an ``opal_server.scopes.task`` that logs while it is imported."""

    def find_spec(self, fullname, path, target=None):
        if fullname == "opal_server.scopes.task":
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def exec_module(self, module):
        logger.debug("import-time record")

        class ScopesPolicyWatcherTask:
            @staticmethod
            def preload_scopes():
                pass

        module.ScopesPolicyWatcherTask = ScopesPolicyWatcherTask


@pytest.fixture
def import_logging_scopes_task(monkeypatch):
    monkeypatch.delitem(sys.modules, "opal_server.scopes.task")
    monkeypatch.delattr(opal_server.scopes, "task")
    monkeypatch.setattr(sys, "meta_path", [_FakeScopesTaskModule(), *sys.meta_path])


def test_when_ready_configures_logs_before_importing_scopes_task(
    master_logs, gunicorn_conf, import_logging_scopes_task, monkeypatch
):
    monkeypatch.setattr(opal_common_config, "LOG_LEVEL", "DEBUG")

    _run_when_ready(gunicorn_conf, master_logs, monkeypatch, scopes=True)

    assert master_logs.default_records == []
    assert ("DEBUG", "import-time record") in master_logs.configured()


def test_import_time_record_reaches_default_handler_when_configure_logs_is_skipped(
    master_logs, gunicorn_conf, import_logging_scopes_task, monkeypatch
):
    monkeypatch.setattr(gunicorn_conf, "configure_logs", lambda: None)

    _run_when_ready(gunicorn_conf, master_logs, monkeypatch, scopes=True)

    assert ("DEBUG", "import-time record") in master_logs.default_records


@pytest.mark.parametrize(
    "configure_logs_runs", [True, False], ids=["configured", "control-skipped"]
)
def test_when_ready_configures_logs_even_when_opal_server_is_absent(
    configure_logs_runs, master_logs, gunicorn_conf, monkeypatch
):
    """The client images share gunicorn_conf.py and have no opal_server."""
    monkeypatch.setitem(sys.modules, "opal_server.scopes.task", None)
    if not configure_logs_runs:
        monkeypatch.setattr(gunicorn_conf, "configure_logs", lambda: None)

    with master_logs.streams():
        assert gunicorn_conf.when_ready(None) is None
    logger.info("after when_ready")

    if configure_logs_runs:
        assert master_logs.default_records == []
        assert master_logs.configured() == [("INFO", "after when_ready")]
    else:
        assert master_logs.default_records == [("INFO", "after when_ready")]


@pytest.mark.parametrize(
    "configure_logs_runs", [True, False], ids=["configured", "control-skipped"]
)
def test_when_ready_routes_stdlib_logging_to_the_configured_sink(
    configure_logs_runs, master_logs, gunicorn_conf, monkeypatch
):
    """configure_logs() also takes over stdlib logging in the master, so a
    third-party library's records, INFO included, land in the configured sink
    at their level; in a fresh process they never reach loguru at all."""
    monkeypatch.setitem(sys.modules, "opal_server.scopes.task", None)
    if not configure_logs_runs:
        monkeypatch.setattr(gunicorn_conf, "configure_logs", lambda: None)

    with master_logs.streams():
        gunicorn_conf.when_ready(None)
    third_party = logging.getLogger("some.third_party.lib")
    third_party.info("stdlib info")
    third_party.warning("stdlib warning")

    if configure_logs_runs:
        assert master_logs.configured() == [
            ("INFO", "stdlib info"),
            ("WARNING", "stdlib warning"),
        ]
    else:
        assert master_logs.default_records == []


def test_preload_scopes_configures_logging_when_nothing_did(
    master_logs, stub_preload, monkeypatch
):
    """A custom GUNICORN_CONF may call preload_scopes() without when_ready's
    configure_logs(); the preload then configures logging itself."""
    monkeypatch.setattr(opal_server_config, "SCOPES", True)

    with master_logs.streams():
        task_module.ScopesPolicyWatcherTask.preload_scopes()

    assert master_logs.default_records == []
    assert ("INFO", "Preloading repo clones for scopes") in master_logs.configured()
    assert CREDENTIAL not in master_logs.stream.getvalue()
    # Recorded, so a later preload in this process keeps these sinks.
    assert opal_logger.logs_configured()


def test_preload_scopes_keeps_logging_already_configured(
    master_logs, stub_preload, monkeypatch
):
    """Once logging is configured (as when_ready does), preload must not
    replace the sinks already in place."""
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_logger, "_logs_configured", True)
    task_module.ScopesPolicyWatcherTask.preload_scopes()
    logger.info("after preload")

    received = [m for _, m in master_logs.default_records]
    assert "Preloading repo clones for scopes" in received
    assert "after preload" in received

    # Control: configure_logs() is observable here as replacing the sink.
    with master_logs.streams():
        configure_logs()
    logger.info("after configure_logs")
    assert "after configure_logs" not in [m for _, m in master_logs.default_records]
