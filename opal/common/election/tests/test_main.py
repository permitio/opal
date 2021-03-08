import os
import enum

from functools import partial
from typing import Dict, Optional

from fastapi import FastAPI
from fastapi.websockets import WebSocket
from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint

from opal.common.election.base import LeaderElectionBase
from opal.common.election.uvicorn_worker_pid import UvicornWorkerPidLeaderElection
from opal.common.election.pubsub_bully import PubSubBullyLeaderElection

# Configurable
PORT = int(os.environ.get("PORT") or "9110")
BASE_URL = f"http://localhost:{PORT}"
ELECTION_ROUTE = "/election"
WS_ROUTE = "/ws"
BROADCAST_URI = os.environ.get("BROADCAST_URI", "postgres://localhost/acalladb")
ELECTED_KEY = "elected"
PID_KEY = "pid"

class ElectionAlgorithm(str, enum.Enum):
    UVICORN_PID = 'UVICORN_PID'
    PUBSUB_BULLY = 'PUBSUB_BULLY'


def setup_pubsub_endpoint(app: FastAPI):
    """
    setup a pub/sub endpoint on the fastapi server
    """
    endpoint = PubSubEndpoint(broadcaster=BROADCAST_URI)

    @app.websocket(WS_ROUTE)
    async def websocket_rpc_endpoint(websocket: WebSocket):
        async with endpoint.broadcaster:
            await endpoint.main_loop(websocket)


def setup_election_on_startup(
    app: FastAPI,
    result_storage: Dict[str, Optional[bool]],
    election_algorithm: ElectionAlgorithm
):
    """
    setup a startup event callback that runs an election and saves the result
    to a dict for later serving it in another api route.
    """
    if election_algorithm == ElectionAlgorithm.UVICORN_PID:
        election_cls = UvicornWorkerPidLeaderElection()
    else:
        election_cls = PubSubBullyLeaderElection(server_uri=f"{BASE_URL}{WS_ROUTE}")

    async def run_election(election: LeaderElectionBase, result: Dict[str, Optional[bool]]):
        result[ELECTED_KEY] = await election.elect()

    on_startup = partial(run_election, election_cls, result_storage)

    @app.on_event("startup")
    async def startup_event():
        return await on_startup()


def setup_api_route_to_return_election_result(
    app: FastAPI,
    result_storage: Dict[str, Optional[bool]]
):
    """
    setups an api route that returns the election result for current worker process
    """
    @app.get(ELECTION_ROUTE)
    def election_result_endpoint():
        return {
            PID_KEY: os.getpid(),
            ELECTED_KEY: result_storage[ELECTED_KEY]
        }


def create_app(election_algorithm: ElectionAlgorithm) -> FastAPI:
    """
    setups a uvicorn server that runs the worker pid election algorithm,
    and can return the result of the election.
    """
    app =  FastAPI()

    result_storage: Dict[str, Optional[bool]] = {ELECTED_KEY: None}

    if election_algorithm == ElectionAlgorithm.PUBSUB_BULLY:
        setup_pubsub_endpoint(app)

    setup_election_on_startup(app, result_storage, election_algorithm)
    setup_api_route_to_return_election_result(app, result_storage)

    return app

def create_app_with_uvicorn_pid_election() -> FastAPI:
    return create_app(ElectionAlgorithm.UVICORN_PID)

def create_app_with_bully_via_pubsub_election() -> FastAPI:
    return create_app(ElectionAlgorithm.PUBSUB_BULLY)