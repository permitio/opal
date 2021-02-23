import asyncio
import aiohttp
import threading

from typing import Tuple, Dict
from fastapi import Response


async def proxy_response(response: aiohttp.ClientResponse):
    content = await response.text()
    return Response(
        content=content,
        status_code=response.status,
        headers=dict(response.headers),
        media_type="application/json",
    )


def tuple_to_dict(tup: Tuple[str, str]) -> Dict[str, str]:
    return dict([tup])


def get_authorization_header(token: str) -> Tuple[str, str]:
    return ("Authorization", f"Bearer {token}")


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
        if not self.loop.is_running():
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
