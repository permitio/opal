"""``state_brief`` must build a valid ``ServerStatsBrief`` at any fleet size.

``server_count`` is an ``int`` fed by ``len(servers) / workers``. pydantic v1
truncated a fractional float into the int field; v2 rejects it, which turned
``GET /stats`` into a 500 on every fresh multi-worker boot, throughout every
rolling restart, and permanently whenever replicas run uneven worker counts.
"""

import pytest
from opal_server.statistics import OpalStatistics, ServerStatsBrief


def _stats_with(servers: int, workers: int) -> OpalStatistics:
    stats = OpalStatistics(endpoint=None)
    stats._workers_count = workers
    stats._state.servers = {f"worker-{i}" for i in range(servers)}
    return stats


@pytest.mark.parametrize(
    "servers,workers,expected",
    [
        (1, 4, 0),  # fresh boot: only this worker has keepalived
        (3, 4, 0),  # mid rollout
        (4, 4, 1),  # fully synced single replica
        (5, 4, 1),  # uneven worker counts across replicas
        (8, 4, 2),  # two fully synced replicas
        (1, 1, 1),  # single worker deployment
    ],
)
def test_state_brief_survives_partial_keepalive(servers, workers, expected):
    brief = _stats_with(servers, workers).state_brief

    assert isinstance(brief, ServerStatsBrief)
    assert brief.server_count == expected
    assert isinstance(brief.server_count, int)


def test_state_brief_never_raises_across_fleet_sizes():
    """The 500 fired while *constructing* the response model, so sweep it."""
    for workers in range(1, 9):
        for servers in range(0, 33):
            brief = _stats_with(servers, workers).state_brief
            assert brief.server_count == servers // workers
