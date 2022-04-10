from fastapi import APIRouter
from fastapi_websocket_pubsub import PubSubEndpoint

from opal_server.scopes.api import setup_scopes_api


def build_api(pubsub_endpoint: PubSubEndpoint):
    router = APIRouter()
    router.mount("/v1", build_v1(pubsub_endpoint))

    return router


def build_v1(pubsub_endpoint: PubSubEndpoint):
    router = APIRouter()
    router.include_router(setup_scopes_api(pubsub_endpoint))

    return router


