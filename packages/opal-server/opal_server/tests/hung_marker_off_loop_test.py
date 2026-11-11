"""A git command-line op's hung-op marker file I/O runs off the event loop.

Such an op ends on the event loop (its on_gone), and its marker sits on
the clones' volume, whose slowness may be what made the op hang:
removing the op's own marker, and the look for stale markers after a
success, run on a thread of their own, never on the loop. The flags that
say the op returned are set at once, so a marker write still under way
removes its own file.
"""

import asyncio
import os
import threading
import time
from pathlib import Path

import pytest
from opal_common.tests.log_capture import capture_records
from opal_server import git_fetcher
from opal_server.git_fetcher import run_git_cli_op

pytestmark = pytest.mark.fetch_backend("cli")


async def _until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition never held"
        await asyncio.sleep(0.01)


def _marker_files(marker_dir: Path) -> list:
    try:
        return sorted(marker_dir.iterdir())
    except FileNotFoundError:
        return []


@pytest.fixture
def file_io(monkeypatch, tmp_path):
    """The marker dir, and the threads its file I/O ran on, by kind."""
    marker_dir = tmp_path / "clone.hung"
    seen = {"remove": [], "isdir": []}
    remove = git_fetcher._remove_hung_marker
    isdir = os.path.isdir

    def _remove(marker):
        seen["remove"].append(threading.get_ident())
        remove(marker)

    def _isdir(path):
        if Path(path) == marker_dir:
            seen["isdir"].append(threading.get_ident())
        return isdir(path)

    monkeypatch.setattr(git_fetcher, "_remove_hung_marker", _remove)
    monkeypatch.setattr(git_fetcher.os.path, "isdir", _isdir)
    return marker_dir, seen


async def _op_that_hangs_then_returns(marker_dir: Path, *, succeeded: bool):
    """An op that outlives its timeout until its hung-op marker is written,
    then returns."""

    async def _op(on_gone):
        await _until(lambda: _marker_files(marker_dir))
        on_gone(succeeded)

    await run_git_cli_op(
        _op,
        timeout=0.05,
        busy_key="hung-0",
        marker_dir=marker_dir,
        mark_when_hung=True,
    )


@pytest.mark.asyncio
async def test_a_cli_op_s_marker_file_io_never_runs_on_the_event_loop(file_io):
    """One op that succeeds within its timeout (the look for stale markers),
    then one that outlives it and returns (the removal of its marker).

    Mutation: calling the marker I/O inline in _HungOpMarker.returned, as
    a libgit2 op's thread does, runs it on the loop.
    """
    marker_dir, seen = file_io
    loop_thread = threading.get_ident()

    async def _quick(on_gone):
        on_gone(True)

    await run_git_cli_op(_quick, timeout=30, busy_key="quick-0", marker_dir=marker_dir)
    await _until(lambda: seen["isdir"])
    await _op_that_hangs_then_returns(marker_dir, succeeded=False)
    await _until(lambda: not _marker_files(marker_dir))

    assert seen["isdir"] and seen["remove"]
    assert loop_thread not in seen["isdir"] + seen["remove"]


@pytest.mark.asyncio
async def test_a_marker_that_cannot_be_removed_leaves_the_op_s_outcome_alone(
    file_io, monkeypatch
):
    """The removal failing with a plain OSError on its thread: a WARNING,
    the marker stays, and the op returns as it would have."""
    marker_dir, _ = file_io
    unlink = Path.unlink

    def _unlink(self, *args, **kwargs):
        if self.parent == marker_dir:
            raise OSError(5, "Input/output error")
        return unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _unlink)

    with capture_records() as logs:
        result = await _op_that_hangs_then_returns(marker_dir, succeeded=True)
        await _until(
            lambda: any("hung-op marker" in r["message"] for r in logs.emitted)
        )

    assert result is None
    assert len(_marker_files(marker_dir)) == 1
    warnings = [r for r in logs.emitted if "hung-op marker" in r["message"]]
    assert [r["level"].name for r in warnings] == ["WARNING"]
    assert warnings[0]["message"].startswith("Could not remove hung-op marker ")


@pytest.mark.asyncio
async def test_an_op_returning_while_its_marker_is_written_leaves_no_marker(
    monkeypatch, tmp_path
):
    """Returned() sets the op's flags at once, on the loop: a marker write that
    started before it removes its own file once it sees them."""
    marker_dir = tmp_path / "clone.hung"
    touched = threading.Event()
    go_on = threading.Event()
    touch = Path.touch

    def _slow_touch(self, *args, **kwargs):
        touch(self, *args, **kwargs)
        touched.set()
        go_on.wait(10)

    monkeypatch.setattr(Path, "touch", _slow_touch)

    async def _op(on_gone):
        await _until(touched.is_set)
        on_gone(False)
        go_on.set()

    await run_git_cli_op(
        _op, timeout=0.05, busy_key="race-0", marker_dir=marker_dir, mark_when_hung=True
    )
    await _until(lambda: not _marker_files(marker_dir))


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["failed", "timed out"])
async def test_an_op_that_did_not_succeed_in_time_leaves_other_markers(tmp_path, how):
    """Only an op that succeeds within its timeout says the clone works: one
    that failed, or ran past its timeout without a marker of its own, leaves
    the markers of earlier hangs where they are.

    Mutation: looking for stale markers after every return clears them.
    """
    marker_dir = tmp_path / "clone.hung"
    marker_dir.mkdir()
    earlier = marker_dir / "other-host-1-1-0000"
    earlier.write_text("")

    async def _op(on_gone):
        if how == "timed out":
            await asyncio.sleep(0.1)
        on_gone(how == "timed out")

    await run_git_cli_op(
        _op,
        timeout=0.05 if how == "timed out" else 30,
        busy_key="other-0",
        marker_dir=marker_dir,
    )
    await asyncio.sleep(0.2)

    assert earlier.exists()
