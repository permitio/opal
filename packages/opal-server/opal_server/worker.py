"""
OPAL background worker process
"""
import json
from pathlib import Path

import requests
from celery import Celery, current_app, current_task

from opal_server.scopes.pullers import create_puller
from opal_server.scopes.scope_store import ScopeConfig
from opal_server.config import opal_server_config

app = Celery('opal-worker',
             broker=opal_server_config.REDIS_URL,
             backend=opal_server_config.REDIS_URL)


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        10 * 60.0,  # 10 minutes
        periodic_check.s(opal_server_config.PRIMARY_URL)
    )


@app.task
def fetch_source(base_dir: str, scope_json: str):
    scope = ScopeConfig.parse_obj(json.loads(scope_json))
    puller = create_puller(Path(base_dir), scope)

    puller.pull()
    return scope.scope_id


@app.task
def setup_periodic_check():
    origin = current_task.request.hostname
    current_app.add_periodic_task(
        1 * 60.0,  # 10 minutes
        periodic_check.s(origin)
    )


@app.task
def periodic_check(opal_url: str):
    requests.post(f'{opal_url}/api/v1/scopes/periodic-check')
