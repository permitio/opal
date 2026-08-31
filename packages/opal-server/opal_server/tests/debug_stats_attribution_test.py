"""Allocation attribution for the /internal stats endpoint.

The cache counters already there answer "are the caches big?". On prod-us that
question is now closed -- 157 sources, flat since boot -- while RSS keeps
climbing ~129 MB/h with a flat scope count, flat thread count, and no clone
activity. So the counters eliminate a suspect but name no culprit, and nothing
else deployed attributes an allocation.

These three additions do:

* ``libgit2_cache_bytes`` -- libgit2 keeps its own object cache (256 MB cap by
  default, never tuned here). It is invisible to gc, to tracemalloc and to any
  Python object census, so flat Python state with climbing RSS is exactly its
  signature. One cheap read rules it in or out.
* ``tracemalloc`` -- names the Python file and line holding the memory, when the
  operator started tracing. Reported only when already tracing: starting it from
  here would double the process's bookkeeping without asking.
* ``object_counts`` -- a gc census catches a growing container the cache
  counters do not cover. It walks every object under the GIL, so it is opt-in
  per request and never runs by default.

Together they answer the one question that decides where the hunt goes next:
Python or native.
"""
import gc
import tracemalloc

import pytest
from opal_server import debug_stats
from opal_server.debug_stats import git_fetcher_cache_stats


def test_libgit2_cache_is_always_reported():
    """Catches leaving the native cache out: it is the only suspect here that no
    Python-level tool can see, and reading it costs nothing."""
    stats = git_fetcher_cache_stats()

    used, cap = stats["libgit2_cache_bytes"]
    assert isinstance(used, int) and isinstance(cap, int)
    assert used >= 0 and cap > 0


def test_libgit2_cache_degrades_when_pygit2_lacks_it(monkeypatch):
    """Catches assuming the attribute exists: a diagnostic endpoint that 500s on
    an older pygit2 is worse than one reporting it cannot see the value."""

    class _NoSettings:
        pass

    monkeypatch.setattr(debug_stats, "pygit2", _NoSettings())

    stats = git_fetcher_cache_stats()

    assert stats["libgit2_cache_bytes"] is None


def test_tracemalloc_absent_when_not_tracing():
    """Catches reporting a zero as though it were a measurement.

    Not tracing and tracing-with-nothing-allocated must not look alike.
    """
    if tracemalloc.is_tracing():
        tracemalloc.stop()

    stats = git_fetcher_cache_stats()

    assert stats["tracemalloc"] == {"tracing": False}


def test_tracemalloc_reports_top_allocators_when_tracing():
    """Catches wiring the key without the snapshot: the whole point is the
    file:line of whoever is holding the memory."""
    tracemalloc.start(1)
    try:
        ballast = [bytearray(50_000) for _ in range(40)]  # noqa: F841

        stats = git_fetcher_cache_stats()
    finally:
        tracemalloc.stop()

    tm = stats["tracemalloc"]
    assert tm["tracing"] is True
    assert tm["traced_kb"] > 0
    assert tm["peak_kb"] >= tm["traced_kb"]
    assert len(tm["top"]) > 0
    first = tm["top"][0]
    assert "location" in first and "size_kb" in first
    # Sorted biggest-first, or the operator reads noise off the top of the list.
    sizes = [entry["size_kb"] for entry in tm["top"]]
    assert sizes == sorted(sizes, reverse=True)


def test_object_census_is_off_by_default():
    """Catches making the gc walk unconditional: it traverses every object under
    the GIL, which on a multi-GB worker is a stall, not a stat."""
    stats = git_fetcher_cache_stats()

    assert "object_counts" not in stats


def test_object_census_returns_top_types_when_asked():
    """Catches returning the raw census: thousands of type names is not a
    diagnostic, and the caller asked for a bounded list."""
    keep = [dict() for _ in range(500)]  # noqa: F841
    gc.collect()

    stats = git_fetcher_cache_stats(top_objects=5)

    counts = stats["object_counts"]
    assert len(counts) == 5
    values = [c["count"] for c in counts]
    assert values == sorted(values, reverse=True)
    assert all("type" in c and "count" in c for c in counts)


@pytest.mark.parametrize("bad", [0, -1])
def test_object_census_stays_off_for_non_positive_values(bad):
    """Catches treating 0 as 'all': the parameter is a top-N bound, and 0 must
    mean off rather than the most expensive possible answer."""
    stats = git_fetcher_cache_stats(top_objects=bad)

    assert "object_counts" not in stats
