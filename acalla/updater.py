import threading
import time

from typing import Callable

from .constants import UPDATE_INTERVAL_IN_SEC
from .client import authorization_client
from .enforcer import enforcer_factory

class PolicyUpdater:
    def __init__(self, update_interval=UPDATE_INTERVAL_IN_SEC):
        self.set_interval(update_interval)
        self._thread = threading.Thread(target=self._run, args=())
        self._thread.daemon = True

    def set_interval(self, update_interval):
        self._interval = update_interval

    def on_interval(self, callback: Callable):
        self._callback = callback

    def start(self):
        if self._interval is not None:
            self._thread.start()

    def _run(self):
        while True:
            time.sleep(self._interval)
            self._callback()


policy_updater = PolicyUpdater()


def update_policy():
    policy = authorization_client.fetch_policy()
    enforcer_factory.set_policy(policy)


def update_policy_data():
    policy_data = authorization_client.fetch_policy_data()
    enforcer_factory.set_policy_data(policy_data)
