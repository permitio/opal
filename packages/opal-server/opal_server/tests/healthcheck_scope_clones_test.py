"""OPAL_SCOPES_READY_REQUIRED_REPOS: /healthcheck answers 503 until every clone
of each required repository has landed, as each worker sees it once.

A clone counts only once it has finished (git_fetcher.clone_landed): a
directory a clone is still writing never does. Once a worker has seen a clone
landed it does not look again, so a later failed fetch, a remote that is
down, or the clone deleted and cloned again never fails readiness.
"""

import asyncio
import hashlib
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import List

import opal_server.scopes.readiness as readiness_module
import opal_server.scopes.task as task_module
import pygit2
import pytest
from opal_common.http_utils import redact_url
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource, NoAuthData
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, PolicyFetcherCallbacks
from opal_server.pubsub_resilience import ReconnectingBroadcaster
from opal_server.scopes.readiness import (
    RequiredClonesLatch,
    required_clones,
    validate_required_repos,
    warn_unmatched_required_repos,
)
from opal_server.scopes.service import ScopesService
from opal_server.server import OpalServer
from starlette.testclient import TestClient

# The default backend; a test that depends on the backend names its own.
pytestmark = pytest.mark.fetch_backend("cli")

_URL = "https://git.example/policy.git"
_OTHER = "git@git.example:org/other.git"


def _ids(url: str, shards: int) -> List[str]:
    """The clone directory names of ``url``, worked out here rather than by the
    code under test."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return [f"{digest}-{i}" for i in range(shards)]


def _git_dir(base: Path, source_id: str) -> Path:
    return base / "git_sources" / source_id / ".git"


def _landed(base: Path, source_id: str) -> Path:
    """A clone whose config records that its clone finished, as _clone() writes
    it."""
    clone = base / "git_sources" / source_id
    pygit2.init_repository(str(clone))
    pygit2.Config(str(clone / ".git" / "config"))["opal.cloned"] = True
    return clone


def _mid_clone(base: Path, source_id: str) -> Path:
    """What a libgit2 clone leaves in place while it still writes its refs: a
    repository, an empty FETCH_HEAD, no checkout and no record."""
    clone = base / "git_sources" / source_id
    pygit2.init_repository(str(clone))
    (clone / ".git" / "FETCH_HEAD").write_text("")
    return clone


@pytest.fixture(autouse=True)
def _fresh(monkeypatch, tmp_path):
    """A latch that has seen nothing, scopes on, and a BASE_DIR of the test's
    own; the setting itself is left to each test."""
    monkeypatch.setattr(required_clones, "_landed", set())
    monkeypatch.setattr(readiness_module, "_unmatched_warned", set())
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 1)
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [])


@pytest.fixture
def required(monkeypatch):
    def _set(*urls: str) -> None:
        monkeypatch.setattr(
            opal_server_config, "SCOPES_READY_REQUIRED_REPOS", list(urls)
        )

    return _set


@pytest.fixture(scope="module")
def _server():
    """One server for the module, built with scopes off (no Redis, no git
    checks): the route reads the settings at each request."""
    scopes = opal_server_config.SCOPES
    opal_server_config.SCOPES = False
    try:
        return OpalServer(
            init_policy_watcher=False, broadcaster_uri=None, enable_jwks_endpoint=False
        )
    finally:
        opal_server_config.SCOPES = scopes


class _Probe:
    """GET /healthcheck when called; ``server`` is the server."""

    def __init__(self, server: OpalServer) -> None:
        self.server = server
        self._client = TestClient(server.app)

    def __call__(self):
        return self._client.get("/healthcheck")


@pytest.fixture
def probe(_server, monkeypatch):
    """The module's server, whose broadcaster a test may replace for itself."""
    monkeypatch.setattr(_server.pubsub, "broadcaster", _server.pubsub.broadcaster)
    return _Probe(_server)


@pytest.fixture
def gauges(monkeypatch):
    seen = []
    monkeypatch.setattr(
        metrics,
        "gauge",
        lambda name, value, tags=None: seen.append((name, value, tags)),
    )
    return seen


@pytest.fixture
def infos():
    messages = []
    sink = logger.add(lambda m: messages.append(m.record["message"]), level="INFO")
    yield messages
    logger.remove(sink)


# --- the route --------------------------------------------------------------------


@pytest.mark.fetch_backend("libgit2")
def test_healthcheck_waits_for_every_shard_of_a_required_repo(
    probe, required, tmp_path, monkeypatch
):
    # A start refuses this (validate_required_repos); the latch itself
    # counts every index.
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    required(_URL)
    ids = _ids(_URL, 3)

    first = probe()
    for sid in ids:
        _mid_clone(tmp_path, sid)
    mid_clone = probe()
    for sid in ids:
        pygit2.Config(str(_git_dir(tmp_path, sid) / "config"))["opal.cloned"] = True
    landed = probe()

    assert first.status_code == 503
    assert first.json() == {
        "status": "error",
        "scopes": "clones missing",
        "missing": ids,
    }
    assert mid_clone.status_code == 503 and mid_clone.json()["missing"] == ids
    assert landed.status_code == 200 and landed.json() == {"status": "ok"}


@pytest.mark.fetch_backend("libgit2")
def test_healthcheck_names_only_the_missing_shard(
    probe, required, tmp_path, monkeypatch
):
    # A start refuses this (validate_required_repos); the latch itself
    # counts every index.
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    required(_URL)
    ids = _ids(_URL, 3)
    _landed(tmp_path, ids[0])
    _landed(tmp_path, ids[2])

    assert probe().json()["missing"] == [ids[1]]


def test_cli_requires_one_clone_whatever_the_shards(
    probe, required, tmp_path, monkeypatch
):
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    required(_URL)

    assert probe().json()["missing"] == _ids(_URL, 1)
    _landed(tmp_path, _ids(_URL, 1)[0])
    assert probe().status_code == 200


def test_every_required_repo_is_waited_for_in_the_settings_order(
    probe, required, tmp_path
):
    required(_URL, _OTHER)
    assert probe().json()["missing"] == _ids(_URL, 1) + _ids(_OTHER, 1)
    _landed(tmp_path, _ids(_URL, 1)[0])
    assert probe().json()["missing"] == _ids(_OTHER, 1)


def test_a_repo_named_twice_is_waited_for_once(probe, required):
    required(_URL, _URL)
    assert probe().json()["missing"] == _ids(_URL, 1)


@pytest.mark.fetch_backend("libgit2")
@pytest.mark.parametrize(
    "leftover",
    ["empty FETCH_HEAD", "no .git", "corrupt config"],
)
def test_what_a_clone_still_writing_leaves_is_not_landed(
    probe, required, tmp_path, leftover
):
    required(_URL)
    sid = _ids(_URL, 1)[0]
    if leftover == "empty FETCH_HEAD":
        _mid_clone(tmp_path, sid)
    elif leftover == "no .git":
        (tmp_path / "git_sources" / sid).mkdir(parents=True)
    else:
        clone = _mid_clone(tmp_path, sid)
        (clone / ".git" / "config").write_text("[opal\n\tcloned = true\n")

    assert probe().status_code == 503


def test_readiness_stays_200_after_the_clone_is_deleted_once_landed(
    probe, required, tmp_path
):
    """A clone deleted to be cloned again (an invalid repository, say), or a
    remote that is down, must not take a Ready worker out of service."""
    required(_URL)
    clone = _landed(tmp_path, _ids(_URL, 1)[0])
    assert probe().status_code == 200

    shutil.rmtree(clone)
    assert probe().status_code == 200


def test_healthcheck_ignores_clones_with_no_required_repos(probe):
    assert probe().json() == {"status": "ok"}


def test_healthcheck_ignores_required_repos_with_scopes_off(
    probe, required, gauges, monkeypatch
):
    required(_URL)
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    assert probe().json() == {"status": "ok"}
    assert not [
        n for n, _, _ in gauges if n == "opal_server.scopes.ready_clones_missing"
    ]


def test_the_answer_never_carries_a_url(probe, required):
    url = "https://user:s3cr3t-token@git.example/private.git"
    required(url)
    body = probe().text
    assert "s3cr3t" not in body and "git.example" not in body
    assert probe().json()["missing"] == _ids(url, 1)


def test_liveness_stays_200_while_readiness_waits(probe, required):
    required(_URL)
    assert probe().status_code == 503
    client = TestClient(probe.server.app)
    assert client.get("/").status_code == 200


def test_broadcaster_503_still_wins(probe, required):
    required(_URL)
    broadcaster = ReconnectingBroadcaster(
        "memory://", notifier=probe.server.pubsub.notifier, channel="test"
    )
    broadcaster._listen_count = 1
    broadcaster._subscription_task = None
    probe.server.pubsub.broadcaster = broadcaster

    response = probe()
    assert response.status_code == 503
    assert response.json() == {"status": "error", "broadcaster": "unhealthy"}


@pytest.mark.fetch_backend("libgit2")
def test_ready_clones_missing_gauge_counts_the_missing_clones(
    probe, required, gauges, tmp_path, monkeypatch
):
    # A start refuses this (validate_required_repos); the latch itself
    # counts every index.
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    required(_URL)
    _landed(tmp_path, _ids(_URL, 3)[0])
    probe()
    for sid in _ids(_URL, 3)[1:]:
        _landed(tmp_path, sid)
    probe()

    readings = [
        (v, t) for n, v, t in gauges if n == "opal_server.scopes.ready_clones_missing"
    ]
    assert readings == [(2, {"pid": str(os.getpid())}), (0, {"pid": str(os.getpid())})]


def test_no_gauge_without_required_repos(probe, gauges):
    probe()
    assert not [
        n for n, _, _ in gauges if n == "opal_server.scopes.ready_clones_missing"
    ]


# --- the latch ----------------------------------------------------------------------


def test_the_latch_reads_disk_only_for_clones_it_has_not_seen_landed(
    required, tmp_path, monkeypatch
):
    required(_URL, _OTHER)
    latch = RequiredClonesLatch()
    _landed(tmp_path, _ids(_URL, 1)[0])
    assert latch.missing(tmp_path) == _ids(_OTHER, 1)

    read = []
    real = readiness_module.clone_landed
    monkeypatch.setattr(
        readiness_module, "clone_landed", lambda d: read.append(d) or real(d)
    )
    assert latch.missing(tmp_path) == _ids(_OTHER, 1)
    assert read == [_git_dir(tmp_path, _ids(_OTHER, 1)[0])]


def test_the_latch_logs_each_clone_it_sees_landed_once(required, tmp_path, infos):
    required(_URL)
    latch = RequiredClonesLatch()
    latch.missing(tmp_path)
    _landed(tmp_path, _ids(_URL, 1)[0])
    latch.missing(tmp_path)
    latch.missing(tmp_path)

    landed = [m for m in infos if _ids(_URL, 1)[0] in m]
    assert len(landed) == 1 and "readiness" in landed[0]


def test_the_latch_requires_nothing_with_scopes_off(required, monkeypatch, tmp_path):
    required(_URL)
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    assert RequiredClonesLatch().missing(tmp_path) == []


def test_a_forked_worker_inherits_the_latch(tmp_path):
    """gunicorn forks each worker from the master: a worker forked after the
    preload saw a clone landed starts Ready, even while the leader deletes
    that clone to clone it again."""
    script = textwrap.dedent(
        """
        import os, shutil, sys
        from pathlib import Path
        from opal_server.config import opal_server_config as config
        config.SCOPES = True
        config.SCOPES_GIT_FETCH_WITH_CLI = True
        config.SCOPES_READY_REQUIRED_REPOS = [sys.argv[2]]
        from opal_server.scopes.readiness import required_clones
        base = Path(sys.argv[1])
        assert required_clones.missing(base) == [], "the clone has not landed"
        shutil.rmtree(base / "git_sources")
        pid = os.fork()
        if pid == 0:
            os._exit(0 if required_clones.missing(base) == [] else 3)
        _, status = os.waitpid(pid, 0)
        print("child", os.waitstatus_to_exitcode(status))
        print("fresh", len(type(required_clones)().missing(base)))
        """
    )
    _landed(tmp_path, _ids(_URL, 1)[0])
    out = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), _URL],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["child", "0", "fresh", "1"], out.stdout


# --- the setting ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        ["[git@github.com:org/policy.git]"],
        ["[git@github.com:org/a.git", "https://h.example/b.git]"],
        ["https://h.example/a.git", "[git@github.com:org/b.git"],
        ["git@github.com:org/a.git", "https://h.example/b.git]"],
        [""],
        ["  "],
    ],
    ids=["json-list", "json-list-of-two", "opening", "closing", "empty", "blank"],
)
def test_a_setting_that_cannot_name_a_repository_stops_a_scopes_server(
    monkeypatch, value
):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", value)
    with pytest.raises(ValueError, match="OPAL_SCOPES_READY_REQUIRED_REPOS") as e:
        validate_required_repos()
    assert "github.com" not in str(e.value) and "h.example" not in str(e.value)


def test_the_server_refuses_to_start_on_such_a_setting(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", ["[x.git]"])
    with pytest.raises(ValueError, match="comma-separated"):
        OpalServer(
            init_policy_watcher=False, broadcaster_uri=None, enable_jwks_endpoint=False
        )


def test_the_setting_is_not_checked_with_scopes_off(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", False)
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", ["[x.git]"])
    validate_required_repos()


def test_urls_of_every_written_form_pass(monkeypatch):
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    monkeypatch.setattr(
        opal_server_config,
        "SCOPES_READY_REQUIRED_REPOS",
        [
            "https://github.com/org/policy.git",
            "git@github.com:org/policy.git",
            "ssh://git@[::1]:2222/org/policy.git",
            "file:///srv/git/policy.git",
            "/srv/git/policy.git",
        ],
    )
    validate_required_repos()


@pytest.mark.fetch_backend("libgit2")
def test_libgit2_shards_with_required_repos_stop_a_scopes_server(required, monkeypatch):
    """A libgit2 shard no scope's branch maps to never clones, so the server
    would never get Ready."""
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", 3)
    required("https://user:s3cr3t@git.example/policy.git")
    with pytest.raises(ValueError) as e:
        validate_required_repos()
    message = str(e.value)
    for setting in (
        "OPAL_SCOPES_GIT_FETCH_WITH_CLI",
        "OPAL_SCOPES_REPO_CLONES_SHARDS",
        "OPAL_SCOPES_READY_REQUIRED_REPOS",
    ):
        assert setting in message, message
    assert "git.example" not in message and "s3cr3t" not in message


@pytest.mark.parametrize(
    "backend, shards, urls",
    [
        ("libgit2", 1, [_URL]),
        ("cli", 3, [_URL]),
        ("libgit2", 3, []),
    ],
    ids=["libgit2-one-shard", "cli-shards-ignored", "libgit2-nothing-required"],
)
def test_shards_pass_where_every_required_clone_can_land(
    required, monkeypatch, backend, shards, urls
):
    monkeypatch.setattr(
        opal_server_config, "SCOPES_GIT_FETCH_WITH_CLI", backend == "cli"
    )
    monkeypatch.setattr(opal_server_config, "SCOPES_REPO_CLONES_SHARDS", shards)
    required(*urls)
    validate_required_repos()


def _as_read(monkeypatch, raw: str) -> None:
    """Set the setting as the server reads it from the environment."""
    from opal_server.config import OpalServerConfig

    monkeypatch.setenv("OPAL_SCOPES_READY_REQUIRED_REPOS", raw)
    monkeypatch.setattr(
        opal_server_config,
        "SCOPES_READY_REQUIRED_REPOS",
        OpalServerConfig(prefix="OPAL_").SCOPES_READY_REQUIRED_REPOS,
    )


@pytest.mark.parametrize(
    "raw",
    [
        "git@git.example:org/a.git, https://x:p#s3cr3t@h.example/b.git",
        '"https://h.example/a.git"',
        "https://h.example/a\\b.git",
        "https://h.example/a#x.git, https://h.example/b.git",
        "https://h.example/a.git, #https://h.example/b.git",
        "https://h.example/a.git,#https://h.example/b.git",
    ],
    ids=[
        "hash-starts-a-comment",
        "quotes-removed",
        "backslash-removed",
        "hash-drops-later-entries",
        "hash-blanks-an-entry",
        "hash-drops-the-last-entry",
    ],
)
def test_an_entry_the_list_parser_changed_stops_a_scopes_server(monkeypatch, raw):
    """The list is read through shlex: what it hands over is not the URL the
    value writes, so it would name a clone nothing makes."""
    _as_read(monkeypatch, raw)
    assert opal_server_config.SCOPES_READY_REQUIRED_REPOS != [
        part.strip() for part in raw.split(",")
    ]
    with pytest.raises(ValueError, match="OPAL_SCOPES_READY_REQUIRED_REPOS") as e:
        validate_required_repos()
    assert "h.example" not in str(e.value) and "s3cr3t" not in str(e.value)
    assert "#" in str(e.value)


@pytest.mark.parametrize(
    "raw, expected",
    [(f" {_URL} ,{_OTHER} ", [_URL, _OTHER]), ("", [])],
    ids=["two-urls", "empty"],
)
def test_a_plain_value_read_from_the_environment_passes(monkeypatch, raw, expected):
    _as_read(monkeypatch, raw)
    assert opal_server_config.SCOPES_READY_REQUIRED_REPOS == expected
    validate_required_repos()


@pytest.mark.parametrize(
    "raw, position",
    [(f"{_URL},", 2), (f"{_URL}, ", 2), (f"{_URL},,{_OTHER}", 2), ("   ", 1)],
    ids=["trailing-comma", "trailing-comma-space", "two-commas", "spaces"],
)
def test_a_blank_entry_read_from_the_environment_stops_a_scopes_server(
    monkeypatch, raw, position
):
    """Read as is, a blank entry names the clone of an empty URL, which nothing
    makes; the list parser keeps some blanks and drops others."""
    _as_read(monkeypatch, raw)
    with pytest.raises(ValueError, match=f"entry {position} is blank"):
        validate_required_repos()


def test_a_value_set_other_than_from_the_environment_is_checked_as_set(
    monkeypatch,
):
    """A value given another way (a command-line option, say) is not the
    environment's text, which then says nothing about it."""
    monkeypatch.setenv("OPAL_SCOPES_READY_REQUIRED_REPOS", "https://h.example/a#b.git")
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", [_URL])
    validate_required_repos()


def test_the_setting_reads_a_comma_separated_list(monkeypatch):
    from opal_server.config import OpalServerConfig

    monkeypatch.setenv("OPAL_SCOPES_READY_REQUIRED_REPOS", f"{_URL}, {_OTHER}")
    assert OpalServerConfig(prefix="OPAL_").SCOPES_READY_REQUIRED_REPOS == [
        _URL,
        _OTHER,
    ]


def test_the_setting_is_sensitive():
    from opal_server.config import OpalServerConfig

    entry = OpalServerConfig(prefix="OPAL_").entries["SCOPES_READY_REQUIRED_REPOS"]
    assert entry.sensitive


# --- a required URL no stored scope uses -------------------------------------------------


def _scope(scope_id: str, url: str) -> Scope:
    return Scope(
        scope_id=scope_id,
        policy=GitPolicyScopeSource(
            source_type="git", url=url, branch="main", auth=NoAuthData(auth_type="none")
        ),
    )


@pytest.fixture
def warned():
    """The records logged at WARNING or above while the test runs."""
    records = []
    sink = logger.add(lambda m: records.append(m.record), level="WARNING")
    yield records
    logger.remove(sink)


def _unmatched(records) -> List[str]:
    return [
        r["message"]
        for r in records
        if "no stored scope's policy source" in r["message"]
    ]


def test_a_required_url_no_stored_scope_uses_is_warned_about_once(required, warned):
    """A URL written unlike the scopes' (a typo, a missing .git) hashes to a
    clone nothing makes: readiness would wait for it with nothing said."""
    required(_URL, _OTHER)
    scopes = [_scope("a", _OTHER), _scope("b", _OTHER)]
    warn_unmatched_required_repos(scopes)
    warn_unmatched_required_repos(scopes)

    messages = _unmatched(warned)
    assert len(messages) == 1, messages
    assert _URL in messages[0] and _OTHER not in messages[0]
    assert "stored scopes: 2" in messages[0]
    assert "/healthcheck stays 503 until a stored scope uses that URL" in messages[0]


def test_each_required_url_is_warned_about_on_its_own(required, warned):
    required(_URL, _OTHER)
    warn_unmatched_required_repos([])
    messages = _unmatched(warned)
    assert len(messages) == 2
    assert all("stored scopes: 0" in m for m in messages)


def test_each_process_warns_on_its_own(required, warned, monkeypatch):
    """The gunicorn master's preload and the leader worker forked from it each
    log it once."""
    required(_URL)
    warn_unmatched_required_repos([])
    monkeypatch.setattr(readiness_module.os, "getpid", lambda: 1)
    warn_unmatched_required_repos([])
    warn_unmatched_required_repos([])
    assert len(_unmatched(warned)) == 2


def test_no_warning_when_every_required_url_is_a_stored_scopes(required, warned):
    required(_URL)
    warn_unmatched_required_repos([_scope("a", _URL), _scope("b", _OTHER)])
    assert _unmatched(warned) == []


def test_no_warning_without_required_urls(warned):
    warn_unmatched_required_repos([])
    assert _unmatched(warned) == []


def test_a_credential_in_a_required_url_never_reaches_the_log(required, warned):
    url = "https://user:s3cr3t-pass@git.example/private.git?private_token=t0ken-zz"
    required(url)
    warn_unmatched_required_repos([_scope("a", _OTHER)])

    assert _unmatched(warned), "nothing was logged"
    logged = repr([(r["message"], r["extra"]) for r in warned])
    assert "s3cr3t" not in logged and "t0ken" not in logged
    assert redact_url(url) in _unmatched(warned)[0]


def test_the_warning_masks_the_url_without_the_log_scrubber(required, monkeypatch):
    """configure_logs() also scrubs every record; the warning must not rely on
    a scrubber some other setup may not install."""
    url = "https://user:s3cr3t-pass@git.example/private.git?private_token=t0ken-zz"
    required(url)
    calls = []

    class _Logger:
        def warning(self, message, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(readiness_module, "logger", _Logger())
    warn_unmatched_required_repos([])

    assert calls == [{"url": redact_url(url), "count": 0}]
    assert "s3cr3t" not in repr(calls) and "t0ken" not in repr(calls)


class _Store:
    def __init__(self, scopes):
        self._scopes = scopes

    async def all(self):
        return self._scopes


@pytest.mark.asyncio
async def test_a_sync_pass_warns_from_the_scopes_it_read(required, warned, tmp_path):
    """Every pass, the leader's and the pre-fork preload's, goes through
    ScopesService.sync_scopes."""
    required(_URL)
    service = ScopesService(base_dir=tmp_path, scopes=_Store([]), pubsub_endpoint=None)
    await service.sync_scopes(notify_on_changes=False)

    messages = _unmatched(warned)
    assert len(messages) == 1 and "stored scopes: 0" in messages[0]


# --- the preload ----------------------------------------------------------------------


@pytest.fixture
def preload(monkeypatch, preload_sandbox, no_redis):
    """preload_scopes with the scope sync stubbed out: ``on_sync`` runs in its
    place."""
    calls = {"on_sync": lambda: None}

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def sync_scopes(self, *a, **k):
            calls["on_sync"]()

    monkeypatch.setattr(task_module, "ScopesService", _Service)
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)
    monkeypatch.setattr(task_module, "drain_git_ops", lambda timeout: True)
    monkeypatch.setattr(task_module, "shutdown_git_executor", lambda: None)
    monkeypatch.setattr(opal_server_config, "SCOPES", True)
    return calls


def test_the_preload_records_the_clones_it_saw_landed(preload, required, tmp_path):
    """What the gunicorn master's latch holds is what each worker forked from
    it starts with."""
    required(_URL, _OTHER)
    preload["on_sync"] = lambda: _landed(tmp_path, _ids(_URL, 1)[0])
    task_module.ScopesPolicyWatcherTask.preload_scopes()
    shutil.rmtree(tmp_path / "git_sources")
    assert required_clones.missing(tmp_path) == _ids(_OTHER, 1)


def test_the_preload_warns_about_the_required_clones_it_did_not_land(preload, required):
    messages = []
    sink = logger.add(lambda m: messages.append(m.record["message"]), level="WARNING")
    try:
        required(_URL)
        task_module.ScopesPolicyWatcherTask.preload_scopes()
    finally:
        logger.remove(sink)
    assert [m for m in messages if _ids(_URL, 1)[0] in m and "readiness" in m]


def test_the_preload_refuses_such_a_setting_before_any_clone(preload, monkeypatch):
    synced = []
    preload["on_sync"] = lambda: synced.append(1)
    monkeypatch.setattr(opal_server_config, "SCOPES_READY_REQUIRED_REPOS", ["[x.git]"])
    with pytest.raises(ValueError, match="OPAL_SCOPES_READY_REQUIRED_REPOS"):
        task_module.ScopesPolicyWatcherTask.preload_scopes()
    assert synced == []


def test_the_preload_warns_about_a_required_url_no_stored_scope_uses(
    preload_sandbox, no_redis, required, warned, monkeypatch
):
    """Through the preload's own sync pass (no scopes stored, so no git)."""
    monkeypatch.setattr(task_module, "configure_server_metrics", lambda: None)
    required(_URL)
    task_module.ScopesPolicyWatcherTask.preload_scopes()
    messages = _unmatched(warned)
    assert len(messages) == 1 and _URL in messages[0]


# --- end to end, through real clones ---------------------------------------------------


class _Recorder(PolicyFetcherCallbacks):
    async def on_update(self, old_head, head):
        pass


@pytest.mark.fetch_backend("both")
@pytest.mark.asyncio
async def test_readiness_follows_a_real_clone_and_never_counts_it_mid_clone(
    probe, required, tmp_path, monkeypatch, git_http, make_origin
):
    """Polled while a real clone stalls mid-pack (libgit2 writes it in place,
    the git command line beside its path), then after a clone that landed."""
    for name in ("repos", "repos_last_fetched", "repo_locks", "source_backoff"):
        monkeypatch.setattr(GitPolicyFetcher, name, {})
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_FETCH_TIMEOUT", 60.0)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_CLONE_TIMEOUT", None)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_SSH_KNOWN_HOSTS", None)
    monkeypatch.setattr(opal_server_config, "SCOPES_GIT_BACKOFF_BASE_SECONDS", 0)
    origin = make_origin(git_http.root / "repo.git")
    origin.commit("master", {"big.bin": b"x" * (512 * 1024)})
    url = git_http.url("repo.git")
    required(url)
    source = GitPolicyScopeSource(
        source_type="git", url=url, branch="master", auth=NoAuthData(auth_type="none")
    )

    def _sync():
        fetcher = GitPolicyFetcher(tmp_path, "scope-1", source, callbacks=_Recorder())
        return fetcher.fetch_and_notify_on_changes(force_fetch=True)

    git_http.stall_after = 1024
    stalled_sync = asyncio.create_task(_sync())
    for _ in range(500):
        if git_http.stalled.is_set():
            break
        await asyncio.sleep(0.01)
    assert git_http.stalled.is_set(), "the clone never reached the server"
    mid_clone = [(await asyncio.to_thread(probe)).status_code for _ in range(3)]
    git_http.stall_after = None
    git_http.release.set()
    await asyncio.wait_for(stalled_sync, 30)
    git_http.release.clear()
    await asyncio.wait_for(_sync(), 30)
    landed = await asyncio.to_thread(probe)

    assert mid_clone == [503, 503, 503]
    assert landed.status_code == 200, landed.text
