import asyncio
import threading
import logging

from typing import Coroutine

from libws.rpc_event_notifier.event_rpc_client import EventRpcClient
from libws.event_notifier import Topic
from libws.logger import logger

from .constants import POLICY_UPDATES_WS_URL
from .client import authorization_client
from .enforcer import enforcer_factory


class PolicyUpdatesEventRpcClient(EventRpcClient):
    """
    adds a tenant-aware prefix to `EventRpcClient` topic names
    """

    def subscribe(self, client_id: str, topic: Topic, callback: Coroutine):
        topic = f"{client_id}::{topic}"
        super().subscribe(topic, callback)


class AsyncioEventLoopThread(threading.Thread):
    """
    This class enable a syncronous program to run an
    asyncio event loop in a separate thread.

    usage:
    thr = AsyncioEventLoopThread()

    # not yet running
    thr.create_task(coroutine1())
    thr.create_task(coroutine2())

    # will start the event loop and all scheduled tasks
    thr.start()
    """

    def __init__(self, *args, loop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.daemon = True
        self.loop = loop or asyncio.new_event_loop()
        self.running = False

    def create_task(self, coro):
        return self.loop.create_task(coro)

    def run(self):
        self.running = True
        logger.info("starting event loop")
        self.loop.run_forever()

    def run_coro(self, coro):
        """
        can be called from the main thread, but will run the coroutine
        on the event loop thread. the main thread will block until a
        result is returned. calling run_coro() is thread-safe.
        """
        return asyncio.run_coroutine_threadsafe(coro, loop=self.loop).result()

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.join()
        self.running = False


def update_policy():
    policy = authorization_client.fetch_policy()
    enforcer_factory.set_policy(policy)


def update_policy_data():
    policy_data = authorization_client.fetch_policy_data()
    enforcer_factory.set_policy_data(policy_data)


class PolicyUpdater:
    def __init__(self):
        self._thread = AsyncioEventLoopThread(name="PolicyUpdaterThread")
        self._client = PolicyUpdatesEventRpcClient()
        self._client_id = None

    def set_client_id(self, client_id):
        """
        the client_id will identify the tenant.

        i.e: we subscribe to `15074816ba6f4aadac7cf97517373149_policy` topic
        where `15074816ba6f4aadac7cf97517373149` identifies the tenant and
        `policy` identifies the actual topic.
        """
        self._client_id = client_id

    async def _update_policy(self, data=None):
        """
        will run when we get notifications on the policy topic.
        i.e: when rego changes
        """
        reason = "" if data is None else data.get("reason", "periodic update")
        logger.info("Refetching policy (rego)", reason=reason)
        update_policy()

    async def _update_policy_data(self, data=None):
        """
        will run when we get notifications on the policy_data topic.
        i.e: when new roles are added, changes to permissions, etc.
        """
        reason = "" if data is None else data.get("reason", "periodic update")
        logger.info("Refetching policy data", reason=reason)
        update_policy_data()

    def start(self):
        self._client.subscribe(self._client_id, "policy", self._update_policy)
        self._client.subscribe(self._client_id, "policy_data", self._update_policy_data)
        self._thread.create_task(
            self._client.run(f"{POLICY_UPDATES_WS_URL}/{self._client_id}")
        )
        self._thread.start()

    def stop(self):
        self._thread.stop()


policy_updater = PolicyUpdater()
