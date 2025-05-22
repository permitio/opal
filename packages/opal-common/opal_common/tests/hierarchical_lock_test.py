import asyncio
from typing import Coroutine

import pytest
from opal_common.synchronization.hierarchical_lock import HierarchicalLock


async def measure_duration(coro: Coroutine) -> float:
    loop = asyncio.get_event_loop()
    start_time = loop.time()
    await coro
    return loop.time() - start_time


@pytest.mark.asyncio
async def test_non_conflicting_paths():
    lock = HierarchicalLock()

    # Acquire a path for alice and a path for bob
    # They should not block each other
    async def lock_path(path):
        async with lock.lock(path):
            await asyncio.sleep(0.1)

    t1 = lock_path("alice")
    t2 = lock_path("bob")

    # If both tasks complete quickly, the test passes.
    duration = await measure_duration(
        asyncio.wait_for(
            asyncio.gather(t1, t2),
            timeout=10,
        )
    )
    assert duration < 0.2, "Both paths should acquire lock concurrently"


@pytest.mark.asyncio
async def test_siblings_do_not_block():
    lock = HierarchicalLock()

    # Acquire two sibling paths concurrently
    # They should not block each other
    async def lock_sibling(path):
        async with lock.lock(path):
            await asyncio.sleep(0.1)

    t1 = lock_sibling("alice.age")
    t2 = lock_sibling("alice.name")

    duration = await measure_duration(
        asyncio.wait_for(
            asyncio.gather(t1, t2),
            timeout=10,
        )
    )
    assert duration < 0.2, "Both siblings should acquire lock concurrently"


@pytest.mark.asyncio
async def test_conflict_do_not_block_unrelated():
    lock = HierarchicalLock()

    # Acquire two sibling paths concurrently
    # They should not block each other
    async def lock_sibling(path: str, delay: float = 0.1):
        async with lock.lock(path):
            await asyncio.sleep(delay)
            return path

    parent = asyncio.create_task(lock_sibling("parent", 0.2))
    child = lock_sibling("parent.child", 0.1)
    unrelated = lock_sibling("unrelated", 0.1)

    # Wait for all tasks to complete, in the order they complete
    order = []
    for coro in asyncio.as_completed([child, parent, unrelated], timeout=10):
        order.append(await coro)
    assert order == [
        "unrelated",
        "parent",
        "parent.child",
    ], "Unrelated paths should not block"


@pytest.mark.asyncio
async def test_parent_blocks_child():
    lock = HierarchicalLock()

    got_lock_child = asyncio.Event()

    async def lock_parent():
        await lock.acquire("alice")
        # hold lock for some time so child attempts to acquire and is blocked
        await asyncio.sleep(0.2)
        await lock.release("alice")

    async def lock_child():
        await asyncio.sleep(0.1)  # wait a moment so parent acquires first
        await lock.acquire("alice.age")
        got_lock_child.set()
        await lock.release("alice.age")

    parent_task = lock_parent()
    child_task = lock_child()

    # child should not be able to acquire immediately
    # so we expect got_lock_child to not be set before 0.2s
    await asyncio.sleep(0.15)
    assert not got_lock_child.is_set(), "Child should be blocked by parent"

    # let everything finish
    await asyncio.gather(parent_task, child_task)
    assert got_lock_child.is_set(), "Child eventually acquires lock"


@pytest.mark.asyncio
async def test_children_block_parent():
    lock = HierarchicalLock()

    got_lock_parent = asyncio.Event()

    async def lock_child(path, delay=0):
        await asyncio.sleep(delay)
        async with lock.lock(path):
            # hold it for some time
            await asyncio.sleep(0.2)

    async def lock_parent():
        await asyncio.sleep(0.05)  # ensure children get the lock first
        async with lock.lock("alice"):
            got_lock_parent.set()

    c1 = lock_child("alice.age", 0)
    c2 = lock_child("alice.name", 0)
    p = lock_parent()

    # Wait some time so the parent tries to acquire
    # The parent should be blocked while children hold locks
    await asyncio.sleep(0.1)
    # Children have likely acquired their locks by now
    assert not got_lock_parent.is_set(), "Parent should be blocked by child locks"

    await asyncio.gather(c1, c2, p)
    assert got_lock_parent.is_set(), "Parent eventually acquires after children release"


# test same key block each other


@pytest.mark.asyncio
async def test_same_key_blocks():
    lock = HierarchicalLock()

    async def lock_task():
        async with lock.lock("alice"):
            await asyncio.sleep(0.2)

    t1 = lock_task()
    t2 = lock_task()

    duration = await measure_duration(
        asyncio.wait_for(
            asyncio.gather(t1, t2),
            timeout=10,
        )
    )
    assert duration >= 0.4, "Both tasks should not acquire lock concurrently"


@pytest.mark.asyncio
async def test_parent_waits_for_new_child():
    lock = HierarchicalLock()

    # We'll do a scenario:
    # 1) Acquire alice.age, alice.name concurrently
    # 2) Acquire alice -> must wait for both to release
    # 3) While alice is waiting, acquire alice.height
    # 4) Release all children, ensure alice eventually gets lock

    # We track the times we acquire the parent to ensure it's after all children.
    parent_acquired = False

    async def child_locker(path: str, hold: float = 0.1, delay: float = 0.0):
        await asyncio.sleep(delay)
        async with lock.lock(path):
            await asyncio.sleep(hold)

    async def parent_locker():
        nonlocal parent_acquired
        # start after children are running
        await asyncio.sleep(0.05)
        async with lock.lock("alice"):
            parent_acquired = True

    c1 = child_locker("alice.age", hold=0.2, delay=0.0)
    c2 = child_locker("alice.name", hold=0.2, delay=0.0)
    p = parent_locker()

    # after a short moment, start new child 'alice.height'
    c3 = child_locker("alice.height", hold=0.2, delay=0.1)

    await asyncio.gather(c1, c2, c3, p)

    assert parent_acquired, "Parent should eventually acquire after all children"


@pytest.mark.asyncio
async def test_release_on_non_locked_path():
    lock = HierarchicalLock()

    with pytest.raises(RuntimeError):
        await lock.release("non-locked-path")


@pytest.mark.asyncio
async def test_same_task_reacquire_same_key_deadlock():
    # Test whether the same coroutine can re-acquire a path it already holds.
    # By default, a non-reentrant lock should deadlock or raise an error.

    lock = HierarchicalLock()

    async def same_task():
        # Acquire once
        await lock.acquire("alice")
        # This should either block forever or raise an error if not re-entrant
        with pytest.raises(RuntimeError):
            await lock.acquire("alice")
        # Release after the test above
        await lock.release("alice")

    await asyncio.wait_for(
        same_task(),
        timeout=10,
    )
