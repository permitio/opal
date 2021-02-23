import asyncio
import threading

from typing import Tuple


def get_authorization_header(token: str) -> Tuple[str, str]:
    return ("Authorization", f"Bearer {token}")

def sorted_list_from_set(s: set) -> list:
    l = list(s)
    l.sort()
    return l


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
