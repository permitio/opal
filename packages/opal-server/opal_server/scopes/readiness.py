"""Readiness waits for the scope clones of SCOPES_READY_REQUIRED_REPOS.

Each process keeps one latch (``required_clones``). Once it has seen a
required clone landed, it never reads that clone again, so a later failed
fetch, a remote that is down, or the clone deleted and cloned again does not
take a Ready worker out of service. A worker forked from the gunicorn master
inherits what the master's pre-fork preload saw.
"""

import os
import string
from pathlib import Path
from typing import List, Sequence, Set, Tuple

from decouple import Csv
from opal_common.confi.confi import config as settings_reader
from opal_common.http_utils import redact_url
from opal_common.logger import logger
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, clone_landed, git_cli_enabled

_SETTING = "OPAL_SCOPES_READY_REQUIRED_REPOS"

# (pid, url) for each required URL warn_unmatched_required_repos warned about:
# once per URL per process, a worker forked after a warning included.
_unmatched_warned: Set[Tuple[int, str]] = set()


def validate_required_repos() -> None:
    """Stop a scopes server whose SCOPES_READY_REQUIRED_REPOS would keep it
    from Ready for good, before it waits for a clone that never comes.

    The setting is a comma-separated list, read through shlex: a # starts
    a comment, and quotes and backslashes are removed, so an entry holding
    one is not the URL it writes. The entries are checked as the value
    writes them. Written as a JSON list, its first entry starts with "["
    and its last ends with "]". With libgit2 and more than one shard, a
    shard no scope's branch maps to never clones. The entries are never
    logged: a URL can carry a credential.

    Raises:
        ValueError: an entry is blank, starts with "[" or ends with "]", or
            is not what the list was read as; or the setting is set with
            libgit2 and SCOPES_REPO_CLONES_SHARDS above 1.
    """
    if not opal_server_config.SCOPES:
        return
    urls = list(opal_server_config.SCOPES_READY_REQUIRED_REPOS)
    for position, entry in enumerate(_entries_as_written(urls), 1):
        if not entry.strip():
            raise _malformed(position, "is blank")
        if entry.strip().startswith("[") or entry.strip().endswith("]"):
            raise _malformed(position, "starts with [ or ends with ] (a JSON list?)")
        if position > len(urls) or entry != urls[position - 1]:
            raise ValueError(
                f"{_SETTING} entry {position} is not the URL the value writes: "
                "the list is read like a shell word list, so a # starts a "
                "comment and quotes and backslashes are removed. Write each URL "
                "without #, quotes or backslashes (percent-encode them in a "
                "URL's userinfo, as %23, %22, %27 and %5C)"
            )
    if (
        urls
        and not git_cli_enabled()
        and opal_server_config.SCOPES_REPO_CLONES_SHARDS > 1
    ):
        raise ValueError(
            f"{_SETTING} is set while OPAL_SCOPES_GIT_FETCH_WITH_CLI is off and "
            "OPAL_SCOPES_REPO_CLONES_SHARDS is above 1: a shard that no scope's "
            "branch maps to is never cloned, so the server would never get "
            "Ready. Set OPAL_SCOPES_REPO_CLONES_SHARDS=1, turn "
            f"OPAL_SCOPES_GIT_FETCH_WITH_CLI on, or leave {_SETTING} empty"
        )


def _malformed(position: int, problem: str) -> ValueError:
    return ValueError(
        f"{_SETTING} entry {position} {problem}: write the repository URLs "
        "comma-separated, each exactly as the scopes' policy sources write it, "
        "with no brackets or quotes"
    )


def _entries_as_written(urls: List[str]) -> List[str]:
    """The setting's entries as its value writes them, split on commas alone,
    when it was read from the environment or a settings file; else ``urls`` (a
    value given another way, such as a command-line option)."""
    raw = settings_reader(_SETTING, default=None)
    if not isinstance(raw, str) or not raw.strip():
        return urls
    if Csv(strip=string.whitespace)(raw) != urls:
        return urls
    return [part.strip() for part in raw.split(",")]


def warn_unmatched_required_repos(scopes: Sequence[Scope]) -> None:
    """WARN about each SCOPES_READY_REQUIRED_REPOS URL that no stored scope's
    policy source uses, once per URL per process: nothing clones it, so
    /healthcheck stays 503 until a stored scope uses that URL.

    The URL is logged masked, as the fetcher logs URLs.

    Args:
        scopes: every stored scope, as a sync pass read them.
    """
    if not opal_server_config.SCOPES_READY_REQUIRED_REPOS:
        return
    used = {scope.policy.url for scope in scopes}
    pid = os.getpid()
    for url in opal_server_config.SCOPES_READY_REQUIRED_REPOS:
        if url in used or (pid, url) in _unmatched_warned:
            continue
        _unmatched_warned.add((pid, url))
        logger.warning(
            "OPAL_SCOPES_READY_REQUIRED_REPOS names {url}, which no stored scope's "
            "policy source uses (stored scopes: {count}): nothing clones it, so "
            "/healthcheck stays 503 until a stored scope uses that URL. Write "
            "each URL exactly as the scopes' policy sources write it.",
            url=redact_url(url),
            count=len(scopes),
        )


class RequiredClonesLatch:
    """The clones of SCOPES_READY_REQUIRED_REPOS this process has seen landed
    (git_fetcher.clone_landed), never forgotten."""

    def __init__(self) -> None:
        self._landed: Set[str] = set()

    def missing(self, base_dir: Path) -> List[str]:
        """The source ids of the required clones this process has not yet seen
        landed, in the setting's order; empty with scopes off.

        Reads the disk only for those. Every clone of a required repository
        counts: one with the git command line, one per shard index below
        SCOPES_REPO_CLONES_SHARDS with libgit2.

        Args:
            base_dir: BASE_DIR, whose git_sources directory holds the clones.
        """
        if not opal_server_config.SCOPES:
            return []
        clones = GitPolicyFetcher.base_dir(base_dir)
        missing: List[str] = []
        for url in opal_server_config.SCOPES_READY_REQUIRED_REPOS:
            for source_id in GitPolicyFetcher.repo_source_ids(url):
                if source_id in self._landed or source_id in missing:
                    continue
                if clone_landed(clones / source_id / ".git"):
                    self._landed.add(source_id)
                    logger.info(
                        "Required scope clone {source_id} has landed: readiness "
                        "no longer waits for it",
                        source_id=source_id,
                    )
                else:
                    missing.append(source_id)
        return missing


# This process's latch: the /healthcheck route reads it, and the pre-fork
# preload fills it in the gunicorn master before any worker is forked.
required_clones = RequiredClonesLatch()
