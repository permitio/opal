import os
import sys

# Add root opal dir to use local src as package for tests (i.e, no need for python -m pytest)
root_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.path.pardir,
        os.path.pardir,
        os.path.pardir,
        os.path.pardir,
    )
)
sys.path.append(root_dir)
sys.path.append(os.path.dirname(__file__))

import asyncio
from multiprocessing import Process
from functools import partial
from typing import Dict, Optional, Any

import pytest

import uvicorn
import aiohttp
import time

from opal.common.election.uvicorn_worker_pid import UvicornWorkerPidLeaderElection

# Configurable
PORT = int(os.environ.get("PORT") or "9110")
BASE_URL = f"http://localhost:{PORT}"
ELECTION_ROUTE = "/election"
WS_ROUTE = "/ws"
BROADCAST_URI = os.environ.get("BROADCAST_URI", "postgres://localhost/acalladb")
ELECTED_KEY = "elected"
PID_KEY = "pid"


def setup_server(app_factory: str, num_workers: int):
    """
    setups a uvicorn server that runs the worker pid election algorithm,
    and can return the result of the election.
    """
    uvicorn.run(f"test_main:{app_factory}", port=PORT, workers=num_workers, factory=True)

@pytest.fixture(params=['create_app_with_uvicorn_pid_election', 'create_app_with_bully_via_pubsub_election'])
def app_factory(request) -> str:
    """
    returns the factory function to use for fastapi app creation.
    each factory method selects a different election algorithm.
    """
    return request.param

@pytest.fixture(params=[1, 2, 3])
def num_workers(request) -> int:
    """
    this fixture returns the number of worker processes
    """
    return request.param

@pytest.fixture()
def server(app_factory: str, num_workers: int):
    """
    this fixture setups a uvicorn server process
    """
    # Run the server as a separate process
    proc = Process(target=partial(setup_server, app_factory, num_workers), args=())
    proc.start()
    # yield the process as parameter to the test
    yield proc
    # Cleanup after test is finished
    proc.kill()
    time.sleep(1)

@pytest.mark.asyncio
async def test_only_one_worker_is_elected(server, app_factory: str, num_workers: int):
    """
    tests both algorithms (bully over pubsub, worker pid) with different amount of workers:
    1 worker (makes sure one worker can select itself by itself), 2 workers, 3 workers.

    test steps:
    1) waits for the server to run the election algorithm
    2) hits /election until the results for all worker processes are known
    3) verifies that only one worker was elected to be the leader
    """
    await asyncio.sleep(1) # wait for server to start

    worker_leadership_result: Dict[int, bool] = {}
    requests = 0

    # we have no control on which worker process our request will
    # land. therefore we keep track of how many unique workers
    # we have already hit, until we landed in all of them.
    while len(worker_leadership_result.keys()) < num_workers:
        requests += 1
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}{ELECTION_ROUTE}") as response:
                result: Dict[str, Any] = await response.json()
                result_pid: Optional[int] = result.get(PID_KEY, None)
                result_elected: Optional[bool] = result.get(ELECTED_KEY, None)

                if result_pid is not None and result_elected is not None:
                    worker_leadership_result[result_pid] = result_elected

    leaders = [elected for elected in worker_leadership_result.values() if elected]
    assert len(leaders) == 1