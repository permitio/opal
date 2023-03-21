from typing import Any

from fastapi_websocket_pubsub import Topic
from opal_common.logger import logger
from opal_server.config import opal_server_config
from opal_server.policy.watcher.task import BasePolicyWatcherTask
from opal_server.redis import RedisDB
from opal_server.scopes.scope_repository import ScopeRepository


class ScopesPolicyWatcherTask(BasePolicyWatcherTask):
    async def trigger(self, topic: Topic, data: Any):
        logger.info("Webhook listener triggered")
        from opal_server.worker import sync_all_scopes, sync_scope

        if data is not None and isinstance(data, dict):
            # Refresh single scope
            try:
                sync_scope.delay(
                    data["scope_id"],
                    force_fetch=data.get("force_fetch", False),
                    hinted_hash=data.get("hinted_hash"),
                )
            except KeyError:
                logger.warning(
                    "Got invalid keyword args for single scope refresh: %s", data
                )
        else:
            # Refresh all scopes
            sync_all_scopes.delay()
