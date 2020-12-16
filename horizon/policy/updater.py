import asyncio

from typing import Coroutine, List, Tuple

from horizon.logger import get_logger, logger
from horizon.config import POLICY_UPDATES_WS_URL, CLIENT_TOKEN
from horizon.policy.rpc import AuthenticatedEventRpcClient, TenantAwareRpcEventClientMethods
from horizon.utils import AsyncioEventLoopThread
from horizon.policy.fetcher import policy_fetcher
from horizon.enforcer.client import opa

updater_logger = get_logger("Updater")

async def update_policy(**kwargs):
    """
    fetches policy (rego) from backend and updates OPA
    """
    updater_logger.info("Refetching policy (rego)", **kwargs)
    policy = await policy_fetcher.fetch_policy()
    await opa.set_policy(policy)


async def update_policy_data(**kwargs):
    """
    fetches policy data (policy configuration) from backend and updates OPA
    """
    updater_logger.info("Refetching policy data", **kwargs)
    policy_data = await policy_fetcher.fetch_policy_data()
    await opa.set_policy_data(policy_data)


async def refetch_policy_and_update_opa(**kwargs):
    """
    will bring both rego and data from backend, and will inject into OPA.
    """
    await update_policy(**kwargs)
    await update_policy_data(**kwargs)


class PolicyUpdater:
    def __init__(self, token=CLIENT_TOKEN, server_url=POLICY_UPDATES_WS_URL):
        self._thread = AsyncioEventLoopThread(name="PolicyUpdaterThread")
        self._token = token
        self._server_url = server_url

    async def _update_policy(self, data=None):
        """
        will run when we get notifications on the policy topic.
        i.e: when rego changes
        """
        reason = "" if data is None else data.get("reason", "periodic update")
        await update_policy(reason=reason)

    async def _update_policy_data(self, data=None):
        """
        will run when we get notifications on the policy_data topic.
        i.e: when new roles are added, changes to permissions, etc.
        """
        reason = "" if data is None else data.get("reason", "periodic update")
        await update_policy_data(reason=reason)

    def start(self):
        logger.info("Launching updater")
        self._client = AuthenticatedEventRpcClient(
            self._token,
            methods_class=TenantAwareRpcEventClientMethods)
        self._client.subscribe("policy", self._update_policy)
        self._client.subscribe("policy_data", self._update_policy_data)
        self._thread.create_task(
            self._client.run(f"{self._server_url}")
        )
        self._thread.start()

    def stop(self):
        logger.info("Stopping updater")
        self._thread.stop()


policy_updater = PolicyUpdater()
