from fastapi import APIRouter

from opal_server.scopes.api import setup_scopes_api
from opal_server.tasks import setup_tasks_api


def build_api():
    router = APIRouter()
    router.mount("/v1", build_v1())

    return router


def build_v1():
    router = APIRouter()
    router.include_router(setup_scopes_api())
    router.include_router(setup_tasks_api())

    return router


