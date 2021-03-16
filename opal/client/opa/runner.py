import asyncio
import psutil

from typing import Coroutine, Optional

from tenacity import retry, wait_random_exponential

from opal.client.config import OPA_PORT
from opal.client.logger import logger
from opal.client.policy_store.policy_store_client_factory import DEFAULT_POLICY_STORE
from opal.client.opa.logger import pipe_opa_logs

opa = DEFAULT_POLICY_STORE

class OpaRunner:
    """
    Runs Opa in a subprocess
    """
    def __init__(self, port=OPA_PORT):
        self._port = port
        self._stopped = False
        self._process = None
        self._on_opa_start_callbacks = []
        self._should_stop: Optional[asyncio.Event] = None
        self._run_task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    def start(self):
        logger.info("Launching opa runner")
        self._run_task = asyncio.create_task(self._run())

    async def stop(self):
        self._init_events()
        if not self._should_stop.is_set():
            logger.info("Stopping opa runner")
            self._should_stop.set()
            self._terminate_opa()
            await asyncio.sleep(1) # wait for opa process to go down

        if self._run_task is not None:
            await self._run_task
        self._run_task = None

    async def wait_until_done(self):
        if self._run_task is not None:
            await self._run_task

    @property
    def command(self):
        return f"opa run --server -a :{self._port}"

    def _terminate_opa(self):
        logger.info("Stopping OPA")
        self._process.terminate()

    async def _run(self):
        self._init_events()
        while not self._should_stop.is_set():
            for task in asyncio.as_completed([self._run_opa_until_terminated(), self._should_stop.wait()]):
                await task
                break

    @retry(wait=wait_random_exponential(multiplier=0.5, max=10))
    async def _run_opa_until_terminated(self) -> int:
        """
        This function runs opa server as a subprocess.
        it returns only when the process terminates.
        """
        logger.info("Running OPA", command=self.command)
        self._process = await asyncio.create_subprocess_shell(
            self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # waits a second, then runs the callbacks if process is up
        asyncio.get_event_loop().call_later(1, self._run_start_callbacks_if_process_is_up, self._process.pid)

        await asyncio.wait([
            pipe_opa_logs(self._process.stdout),
            pipe_opa_logs(self._process.stderr)
        ])

        return_code = await self._process.wait()
        logger.info("OPA exited with return code: {return_code}", return_code=return_code)
        if return_code > 0: # exception in running opa
            raise Exception(f"OPA exited with return code: {return_code}")
        return return_code

    def on_opa_start(self, callback: Coroutine):
        self._on_opa_start_callbacks.append(callback)

    def _run_start_callbacks_if_process_is_up(self, process_pid):
        if not psutil.pid_exists(process_pid):
            # do nothing, the process went down immediately
            return
        asyncio.create_task(self._run_start_callbacks())

    async def _run_start_callbacks(self):
        return await asyncio.gather(*(callback() for callback in self._on_opa_start_callbacks))

    def _init_events(self):
        if self._should_stop is None:
            self._should_stop = asyncio.Event()

    @staticmethod
    def setup_opa_runner():
        opa_runner = OpaRunner()
        # if opa was down and restarted - its cache is clean,
        # meaning it cannot answer isAllowed queries correctly
        # in that case we rehydrate the cache.
        async def rehydrate_opa():
            logger.info("Rehydrating OPA from cache")
            await opa.rehydrate_opa_from_process_cache()

        opa_runner.on_opa_start(rehydrate_opa)
        return opa_runner