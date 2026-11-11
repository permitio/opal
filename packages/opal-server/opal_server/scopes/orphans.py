"""The orphan sweep: the scopes leader removes the scope clones in BASE_DIR's
git_sources that no stored scope uses (SCOPES_ORPHAN_SWEEP_INTERVAL, off by
default).

Every interval, one look:

1. List the clones: the real directories named like a source id
   (``SOURCE_ID_RE``). Symlinks and every other name (lock files, hung-op
   markers, host keys, ``.libgit2-home``, directories a clone is being made
   in) are neither counted nor removed.
2. Read the store: the scope ids its keys list (``ScopeRepository.ids()``,
   what GET /scopes/ids lists), then the records (``all()``). A listed id
   whose record the listing did not return is read back: found, the listing
   was incomplete and the look decides nothing (store_inconsistent); gone, it
   was deleted in between. A record no read finds, evicted or lost in a
   restore, counts as deleted.
3. Keep the clones the records map to (``GitPolicyFetcher.source_id``) and
   those of SCOPES_READY_REQUIRED_REPOS. Refuse when the store lists no scope
   at all (unless SCOPES_ORPHAN_SWEEP_MAX_SHARE is 1.0), or when more than
   that share of the clones the store must vouch for (all but the required
   ones) are unused: an empty or wrong store looks the same as one whose
   scopes were deleted.
4. A clone unused at two looks at least an interval apart, with no look in
   between finding it used, goes (reclaim_clone_dir_unless_busy), at most
   16 per look, the longest unused first. Right before, holding its
   lock_source, the store is read again: a scope stored since the look that
   uses it keeps it. One that cannot be removed waits one interval, then
   two, four and so on. One a task of this process holds (lock_source, a git
   op in flight) or another process holds (its locks) is kept for the next
   look.
5. In each clone kept, the fetch marks of branches no stored scope of it
   tracks go (remove_stale_fetch_marks).

A refused look, or one that cannot read the store or the clones, forgets
every sighting; after a refusal a clone goes only once two looks in a row
found the store no bigger, so a store being refilled keeps the clones of
the scopes still to come. The sightings live in this process's memory, on
the monotonic clock: a restart or a new leader starts over, which delays a
removal and never hastens one. No broadcast: each server owns its own
clones, and a worker that is not the leader caches no handle of them.
"""

import asyncio
import math
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence, Set, Tuple

from opal_common.async_utils import run_sync
from opal_common.logger import logger
from opal_common.monitoring import metrics
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.git_fetcher import (
    SOURCE_ID_RE,
    GitPolicyFetcher,
    reclaim_clone_dir_unless_busy,
    remove_stale_fetch_marks,
    source_busy,
)
from opal_server.scopes.scope_repository import ScopeNotFoundError, ScopeRepository

# Removals (and failed attempts) per look: a look that finds many clones
# unused at once spreads their removal over several.
_MAX_REMOVALS_PER_SWEEP = 16
# Listed ids whose record the listing did not return that a look reads back;
# beyond it the two listings disagree too much to decide anything.
_MAX_LISTING_GAP_READS = 100
# The longest a clone whose removal failed waits, in intervals.
_MAX_BACKOFF_INTERVALS = 64


def orphan_sweep_interval() -> float:
    """SCOPES_ORPHAN_SWEEP_INTERVAL, or 0 (off) unless positive and finite."""
    value = float(opal_server_config.SCOPES_ORPHAN_SWEEP_INTERVAL)
    return value if math.isfinite(value) and value > 0 else 0.0


def orphan_sweep_max_share() -> float:
    """SCOPES_ORPHAN_SWEEP_MAX_SHARE read as 0 to 1; not a number is 0."""
    value = float(opal_server_config.SCOPES_ORPHAN_SWEEP_MAX_SHARE)
    if math.isnan(value):
        return 0.0
    return min(1.0, max(0.0, value))


@dataclass(frozen=True)
class SweepOutcome:
    """What one look did.

    Attributes:
        outcome: ``removed``, ``nothing``, ``refused``, ``store_error``,
            ``store_inconsistent`` or ``disk_error``.
        counted: The clones counted.
        unused: Those no stored scope uses.
        removed: Those removed.
        failed: Those whose removal failed.
        busy: Those kept because something held them.
        used_again: Those kept because a scope stored since the look's read
            of the store uses them.
        waiting: Those unused for less than an interval so far.
        marks_removed: Stale fetch marks removed from the clones kept.
    """

    outcome: str
    counted: int = 0
    unused: int = 0
    removed: int = 0
    failed: int = 0
    busy: int = 0
    used_again: int = 0
    waiting: int = 0
    marks_removed: int = 0


class _Undecided(Exception):
    """A look that decides nothing: ``outcome`` says why."""

    def __init__(self, outcome: str, why: str, unused: int = 0) -> None:
        super().__init__(why)
        self.outcome = outcome
        self.counted = 0
        self.unused = unused
        self.removed = 0


@dataclass
class _Backoff:
    failures: int
    retry_at: float


def _counted_clones(clones: Path) -> Tuple[Set[str], Set[str]]:
    """The names like a source id in ``clones``: those of real directories, and
    those of symlinks; none when ``clones`` is not there yet.

    Raises:
        OSError: ``clones`` cannot be listed.
    """
    found: Set[str] = set()
    links: Set[str] = set()
    try:
        with os.scandir(clones) as entries:
            for entry in entries:
                if not SOURCE_ID_RE.match(entry.name):
                    continue
                if entry.is_symlink():
                    links.add(entry.name)
                elif entry.is_dir(follow_symlinks=False):
                    found.add(entry.name)
    except FileNotFoundError:
        pass
    return found, links


def _clone_of(scope: Scope) -> Optional[str]:
    """The source id of the clone a scope uses; None for no git source."""
    if not isinstance(scope.policy, GitPolicyScopeSource):
        return None
    return GitPolicyFetcher.source_id(scope.policy)


def _scope_ids_in_clone(clone: Path) -> Set[str]:
    """The scope ids the clone's branches name (``refs/heads/scopes/<id>``,
    loose or packed, the id written in hex when it cannot be a ref name), each
    as written and, when that is hex, decoded too.

    Nothing through a symlink; a clone whose refs cannot be read names
    none.
    """
    git_dir = clone / ".git"
    prefix = "refs/heads/scopes/"
    names: Set[str] = set()
    try:
        with open(git_dir / "packed-refs", encoding="utf-8", errors="replace") as f:
            for line in f:
                ref = line.rstrip("\n").partition(" ")[2]
                if ref.startswith(prefix):
                    names.add(ref[len(prefix) :])
    except OSError:
        pass
    loose = git_dir / "refs" / "heads" / "scopes"
    try:
        real = stat.S_ISDIR(os.lstat(loose).st_mode)
    except OSError:
        real = False
    if real:
        for root, _, files in os.walk(loose, followlinks=False):
            for name in files:
                names.add(os.path.relpath(os.path.join(root, name), loose))
    ids = set(names)
    for name in names:
        try:
            ids.add(bytes.fromhex(name).decode("utf-8"))
        except ValueError:
            continue
    return ids


async def _bounded(read):
    """``read`` bounded by SCOPES_STORE_READ_TIMEOUT (0 or less: no bound), as
    every store read taken under a source's lock_source is.

    Raises:
        _Undecided: the read timed out.
    """
    timeout = opal_server_config.SCOPES_STORE_READ_TIMEOUT
    if timeout <= 0:
        return await read
    try:
        return await asyncio.wait_for(read, timeout=timeout)
    except asyncio.TimeoutError:
        raise _Undecided(
            "store_error", f"reading the scopes took more than {timeout}s"
        ) from None


def _required_source_ids() -> Set[str]:
    return {
        source_id
        for url in opal_server_config.SCOPES_READY_REQUIRED_REPOS
        for source_id in GitPolicyFetcher.repo_source_ids(url)
    }


class OrphanCloneSweeper:
    """The leader's orphan sweep over BASE_DIR's git_sources (see the module
    docstring).

    Args:
        base_dir: BASE_DIR.
        scopes: The scope store (a ScopeRepository).
        interval: Seconds between looks, and the least time between a
            clone's two sightings.
        clock: The monotonic clock the sightings are dated with.
        wall_clock: The clock fetch marks are dated with (epoch seconds).
    """

    def __init__(
        self,
        base_dir: Path,
        scopes: ScopeRepository,
        interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._clones = GitPolicyFetcher.base_dir(base_dir)
        self._scopes = scopes
        self._interval = interval
        self._clock = clock
        self._wall_clock = wall_clock
        # source id -> when a look first found it unused, since none found it used.
        self._first_seen: Dict[str, float] = {}
        self._backoff: Dict[str, _Backoff] = {}
        # Symlinks named like a clone this sweeper warned about, once each.
        self._links_warned: Set[str] = set()
        # None, or since a refusal: -1 until a look is allowed again, then how
        # many scopes the last allowed look read.
        self._refused_since: Optional[int] = None

    async def run(self) -> None:
        """Look every interval, the first one interval after the start, until
        cancelled."""
        logger.info(
            "Orphan sweep: looking for scope clones no stored scope uses in {path} "
            "every {interval:.0f}s, refusing while more than {share:.0%} of them "
            "are unused",
            path=str(self._clones),
            interval=self._interval,
            share=orphan_sweep_max_share(),
        )
        last = self._clock()
        while True:
            # A whole interval by the sightings' clock: a timer that fires a
            # little early would otherwise defer every removal by a look.
            while (left := last + self._interval - self._clock()) > 0:
                await asyncio.sleep(left)
            last = self._clock()
            try:
                await self.sweep_once()
            except Exception:
                self._first_seen.clear()
                logger.exception("Orphan sweep failed; it forgot what it saw")

    async def sweep_once(self) -> SweepOutcome:
        """One look; see the module docstring."""
        try:
            outcome = await self._look()
        except _Undecided as e:
            self._first_seen.clear()
            outcome = SweepOutcome(
                outcome=e.outcome, counted=e.counted, unused=e.unused, removed=e.removed
            )
            logger.warning(
                "Orphan sweep: {outcome}: nothing more removed, and every sighting "
                "forgotten: {why}",
                outcome=e.outcome,
                why=str(e),
            )
        else:
            metrics.gauge("opal_server.scopes.orphan_clone_dirs", outcome.unused)
        metrics.increment(
            "opal_server.scopes.orphan_sweep", tags={"outcome": outcome.outcome}
        )
        logger.info(
            "Orphan sweep: {counted} clone dirs, {unused} unused, {removed} removed, "
            "outcome {outcome} ({failed} failed, {busy} kept busy, {used_again} used "
            "again, {waiting} waiting for a second sighting, {marks} stale fetch "
            "marks removed)",
            counted=outcome.counted,
            unused=outcome.unused,
            removed=outcome.removed,
            outcome=outcome.outcome,
            failed=outcome.failed,
            busy=outcome.busy,
            used_again=outcome.used_again,
            waiting=outcome.waiting,
            marks=outcome.marks_removed,
        )
        return outcome

    async def _look(self) -> SweepOutcome:
        try:
            counted, links = await run_sync(_counted_clones, self._clones)
        except OSError as e:
            raise _Undecided("disk_error", f"cannot list {self._clones}: {e!r}")
        for name in sorted(links - self._links_warned):
            self._links_warned.add(name)
            logger.warning(
                "Orphan sweep: {path} is a symlink, not a scope clone: never "
                "counted or removed",
                path=str(self._clones / name),
            )
        if not counted:
            self._first_seen.clear()
            self._backoff.clear()
            return SweepOutcome(outcome="nothing")
        read_at = self._wall_clock()
        try:
            listed, scopes = await self._read_scopes()
        except _Undecided as e:
            e.counted = len(counted)
            raise
        branches: Dict[str, Set[str]] = {}
        for scope in scopes:
            if isinstance(scope.policy, GitPolicyScopeSource):
                source_id = GitPolicyFetcher.source_id(scope.policy)
                branches.setdefault(source_id, set()).add(scope.policy.branch)
        used = set(branches)
        # The required clones are kept whatever the store says, so they count
        # on neither side of the share: what is judged is what the store must
        # vouch for.
        judged = counted - _required_source_ids()
        unused = judged - used
        try:
            self._refuse_unless_vouched(
                listed, scopes, judged, unused, orphan_sweep_max_share()
            )
        except _Undecided as e:
            e.counted = len(counted)
            raise
        now = self._clock()
        for source_id in list(self._first_seen):
            if source_id not in unused:
                del self._first_seen[source_id]
        for source_id in list(self._backoff):
            if source_id not in unused:
                del self._backoff[source_id]
        if self._refused_since is not None:
            # After a refusal the store may still be refilling: a clone goes
            # only once two looks in a row found the store no bigger.
            if self._refused_since < 0 or len(scopes) > self._refused_since:
                self._first_seen.clear()
                self._refused_since = len(scopes)
            else:
                self._refused_since = None
        for source_id in unused:
            self._first_seen.setdefault(source_id, now)
        due = sorted(
            (
                source_id
                for source_id, seen in self._first_seen.items()
                if now - seen >= self._interval
                and (
                    source_id not in self._backoff
                    or now >= self._backoff[source_id].retry_at
                )
            ),
            key=lambda source_id: (self._first_seen[source_id], source_id),
        )
        waiting = sum(1 for s in unused if now - self._first_seen[s] < self._interval)
        tally = {"removed": 0, "failed": 0, "busy": 0, "used": 0}
        for source_id in due:
            if tally["removed"] + tally["failed"] >= _MAX_REMOVALS_PER_SWEEP:
                break
            try:
                result = await self._reclaim(source_id, now)
            except _Undecided as e:
                e.counted, e.unused, e.removed = (
                    len(counted),
                    len(unused),
                    tally["removed"],
                )
                raise
            if result is not None:
                tally[result] += 1
        marks = 0
        for source_id in sorted(counted & used):
            marks += await self._remove_stale_marks(
                source_id, branches.get(source_id, set()), read_at
            )
        return SweepOutcome(
            outcome="removed" if tally["removed"] else "nothing",
            counted=len(counted),
            unused=len(unused),
            removed=tally["removed"],
            failed=tally["failed"],
            busy=tally["busy"],
            used_again=tally["used"],
            waiting=waiting,
            marks_removed=marks,
        )

    def _refuse_unless_vouched(
        self,
        listed: Set[str],
        scopes: Sequence[Scope],
        judged: Set[str],
        unused: Set[str],
        most: float,
    ) -> None:
        """Refuse the look when the store cannot vouch for its clones: it lists
        no scope at all (unless the guard is off), or more than ``most`` of
        the judged clones are unused.

        Raises:
            _Undecided: refused.
        """
        share = len(unused) / len(judged) if judged else 0.0
        if not listed and not scopes and most < 1.0:
            why = (
                "the scope store lists no scope at all, while "
                f"{len(judged)} scope clones are not required ones"
            )
        elif share > most:
            why = (
                f"{len(unused)} of {len(judged)} scope clones that are not "
                f"required ones ({share:.0%}) are used by no stored scope, more "
                f"than OPAL_SCOPES_ORPHAN_SWEEP_MAX_SHARE ({most:.0%})"
            )
        else:
            return
        self._refused_since = -1
        metrics.gauge("opal_server.scopes.orphan_clone_dirs", len(unused))
        raise _Undecided(
            "refused",
            f"{why}. A store that lost its scopes, or a server pointed at another "
            "store, looks like this; once the store is right again, or with the "
            "setting raised when they really are unused, the sweep goes on",
            unused=len(unused),
        )

    async def _read_scopes(self) -> Tuple[Set[str], Sequence[Scope]]:
        """The scope ids the store's keys list, and every stored scope, once
        the keys and the records agree.

        Raises:
            _Undecided: the store failed, or a listed scope reads back
                although the listing of the records missed it.
        """
        try:
            listed = set(await self._scopes.ids())
            scopes = await self._scopes.all()
        except Exception as e:
            raise _Undecided("store_error", f"reading the scopes failed: {e!r}")
        missed = sorted(listed - {scope.scope_id for scope in scopes})
        if len(missed) > _MAX_LISTING_GAP_READS:
            raise _Undecided(
                "store_inconsistent",
                f"{len(missed)} scopes listed by key are missing from the "
                "listing of the records",
            )
        for scope_id in missed:
            if await self._get(scope_id) is not None:
                raise _Undecided(
                    "store_inconsistent",
                    f"scope {scope_id} is stored, but the listing of the records "
                    "missed it",
                )
        return listed, scopes

    async def _get(self, scope_id: str) -> Optional[Scope]:
        """The stored scope ``scope_id``, None when there is none.

        Raises:
            _Undecided: reading it failed.
        """
        try:
            return await self._scopes.get(scope_id)
        except ScopeNotFoundError:
            return None
        except Exception as e:
            raise _Undecided("store_error", f"reading scope {scope_id} failed: {e!r}")

    async def _user_of(self, source_id: str) -> Optional[str]:
        """The id of a scope stored now whose clone ``source_id`` is: from a
        fresh listing of the records, else (a scope that listing missed) from
        the scope ids the clone's own branches name. For the holder of the
        clone's lock_source, which every sync of it takes.

        Raises:
            _Undecided: the store failed, or a scope the clone's branches
                name maps to it although the listing missed it.
        """
        try:
            scopes = await self._scopes.all()
        except Exception as e:
            raise _Undecided("store_error", f"reading the scopes failed: {e!r}")
        for scope in scopes:
            if _clone_of(scope) == source_id:
                return scope.scope_id
        listed = {scope.scope_id for scope in scopes}
        named = await run_sync(_scope_ids_in_clone, self._clones / source_id)
        for scope_id in sorted(named - listed):
            scope = await self._get(scope_id)
            if scope is not None and _clone_of(scope) == source_id:
                raise _Undecided(
                    "store_inconsistent",
                    f"scope {scope_id}, which a branch of scope clone {source_id} "
                    "names, is stored and uses it, but the listing of the records "
                    "missed it",
                )
        return None

    async def _reclaim(self, source_id: str, now: float) -> Optional[str]:
        """Remove one unused clone: "removed", "busy", "failed", "used" (a
        scope stored since the look uses it), or None when it was gone
        already.

        Raises:
            _Undecided: the store read before the removal failed or was
                incomplete.
        """
        if source_busy(source_id):
            return self._kept_busy(source_id, "a sync, purge or git op of it runs")
        path = str(self._clones / source_id)
        # Not busy: lock_source is taken without waiting, so nothing of this
        # process starts on the clone in between. A scope stored before the
        # read below is found by it; one stored later has its sync wait for
        # this lock, and that sync clones afresh.
        async with GitPolicyFetcher.lock_source(source_id):
            minted = GitPolicyFetcher.repo_locks.get(source_id)
            try:
                user = await _bounded(self._user_of(source_id))
                if user is not None:
                    self._first_seen.pop(source_id, None)
                    logger.warning(
                        "Orphan sweep: keeping scope clone {source_id}: it is used "
                        "by scope {scope_id}, stored since the look read the store",
                        source_id=source_id,
                        scope_id=user,
                    )
                    return "used"
                # Nothing of this process uses the clone: what it cached of
                # it goes first, its pygit2 handle with the packs it maps.
                GitPolicyFetcher.forget_repo(path)
                GitPolicyFetcher.forget_fetches(source_id)
                GitPolicyFetcher.forget_source_backoff(source_id)
                GitPolicyFetcher.forget_repack_due(source_id)
                try:
                    reclaimed = await run_sync(reclaim_clone_dir_unless_busy, path)
                except OSError as e:
                    return self._failed(source_id, now, e)
            finally:
                # Invariant I4: no repo_locks entry for a source no scope uses.
                if GitPolicyFetcher.repo_locks.get(source_id) is minted:
                    GitPolicyFetcher.repo_locks.pop(source_id, None)
        if reclaimed is None:
            self._first_seen.pop(source_id, None)
            return None
        if not reclaimed:
            return self._kept_busy(source_id, "a repack or a git op holds its lock")
        unused_since = self._first_seen.pop(source_id, now)
        self._backoff.pop(source_id, None)
        metrics.increment("opal_server.scopes.orphan_clone_removed")
        logger.info(
            "Orphan sweep: removed scope clone {source_id}, which no stored scope "
            "has used for at least {seconds:.0f}s",
            source_id=source_id,
            seconds=now - unused_since,
        )
        return "removed"

    def _kept_busy(self, source_id: str, why: str) -> str:
        logger.info(
            "Orphan sweep: keeping scope clone {source_id} for now: {why}",
            source_id=source_id,
            why=why,
        )
        return "busy"

    def _failed(self, source_id: str, now: float, err: OSError) -> str:
        entry = self._backoff.get(source_id)
        failures = 1 if entry is None else entry.failures + 1
        wait = self._interval * min(2 ** (failures - 1), _MAX_BACKOFF_INTERVALS)
        self._backoff[source_id] = _Backoff(failures=failures, retry_at=now + wait)
        metrics.increment("opal_server.scopes.orphan_clone_remove_failed")
        logger.warning(
            "Orphan sweep: could not remove scope clone {source_id} (failure "
            "{failures} in a row), trying again in {wait:.0f}s: {err!r}",
            source_id=source_id,
            failures=failures,
            wait=wait,
            err=err,
        )
        return "failed"

    async def _remove_stale_marks(
        self, source_id: str, branches: Set[str], read_at: float
    ) -> int:
        """remove_stale_fetch_marks for one clone kept, under its lock_source;
        0 while it is busy."""
        if source_busy(source_id):
            return 0
        existed = source_id in GitPolicyFetcher.repo_locks
        async with GitPolicyFetcher.lock_source(source_id):
            minted = GitPolicyFetcher.repo_locks.get(source_id)
            try:
                path = self._clones / source_id
                try:
                    removed = await run_sync(
                        remove_stale_fetch_marks, path, branches, read_at
                    )
                except OSError as e:
                    logger.warning(
                        "Orphan sweep: could not remove the stale fetch marks of "
                        "scope clone {source_id}: {err!r}",
                        source_id=source_id,
                        err=e,
                    )
                    return 0
            finally:
                if not existed and GitPolicyFetcher.repo_locks.get(source_id) is minted:
                    GitPolicyFetcher.repo_locks.pop(source_id, None)
        if removed:
            logger.debug(
                "Orphan sweep: removed {count} stale fetch marks of scope clone "
                "{source_id}",
                count=removed,
                source_id=source_id,
            )
        return removed
