"""
OPAL background worker process
"""
import json

import requests
from celery import Celery

from opal_server.scopes.pullers import create_puller
from opal_server.scopes.scope_store import Scope
from opal_server.config import opal_server_config

app = Celery('opal-worker',
             broker=opal_server_config.REDIS_URL,
             backend=opal_server_config.REDIS_URL)


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        opal_server_config.FETCHER_CHECK_INTERVAL,  # 10 minutes
        periodic_check.s(
            opal_server_config.OPAL_URL,
            opal_server_config.SCOPE_API_KEY
        )
    )


@app.task
def fetch_source(base_dir: str, scope_json: str):
    scope = Scope.parse_obj(json.loads(scope_json))
    puller = create_puller(base_dir, scope)

    puller.pull()


@app.task
def periodic_check(opal_url: str, token: str):
    requests.post(
        f'{opal_url}/api/v1/scopes/periodic-check',
        headers={
            'Authorization': f'Bearer: {token}'
        })
