import asyncio
import threading
import logging

from typing import Coroutine, List, Tuple

from fastapi_websocket_rpc.pubsub import EventRpcClient
from fastapi_websocket_rpc.pubsub.rpc_event_methods import RpcEventClientMethods
from fastapi_websocket_rpc.pubsub.event_notifier import Topic
from fastapi_websocket_rpc.websocket.rpc_methods import RpcMethodsBase
from .logger import logger

from .constants import POLICY_UPDATES_WS_URL
from .client import authorization_client
from .enforcer import enforcer_factory


TOPIC_SEPARATOR = "::"


def get_authorization_header(token: str) -> Tuple[str, str]:
    return ("Authorization", f"Bearer {token}")


class AuthenticatedEventRpcClient(EventRpcClient):
    """
    adds HTTP Authorization header before connecting to the server's websocket.
    """
    def __init__(self, token: str, topics: List[Topic] = [], methods_class=None):
        super().__init__(topics=topics, methods_class=methods_class, extra_headers=[get_authorization_header(token)])


class TenantAwareRpcEventClientMethods(RpcEventClientMethods):
    """
    use this methods class when the server uses `TenantAwareRpcEventServerMethods`.
    """
    async def notify(self, subscription=None, data=None):
        self.logger.info("Received notification of event", subscription=subscription, data=data)
        topic = subscription["topic"]
        if TOPIC_SEPARATOR in topic:
            topic_parts = topic.split(TOPIC_SEPARATOR)
            if len(topic_parts) > 1:
                topic = topic_parts[1] # index 0 holds the app id
        await self.client.act_on_topic(topic=topic, data=data)


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
        self._client = AuthenticatedEventRpcClient(
            authorization_client.token,
            methods_class=TenantAwareRpcEventClientMethods)
        self._client.subscribe("policy", self._update_policy)
        self._client.subscribe("policy_data", self._update_policy_data)
        self._thread.create_task(
            self._client.run(f"{POLICY_UPDATES_WS_URL}")
        )
        self._thread.start()

    def stop(self):
        self._thread.stop()


policy_updater = PolicyUpdater()
