import json
import asyncio
import logging
import time
import psutil

from typing import Coroutine

from tenacity import retry, wait_random_exponential

from opal.client.config import OPA_PORT
from opal.client.logger import get_logger
from opal.client.utils import AsyncioEventLoopThread
from opal.client.policy_store.policy_store_client_factory import DEFAULT_POLICY_STORE, PolicyStoreTypes

opa = DEFAULT_POLICY_STORE

logger = get_logger("Opal Client")
runner_logger = get_logger("Opa Runner")
opa_logger = get_logger("OPA")

def logging_level_from_string(level: str) -> int:
    """
    logger.log() requires an int logging level
    """
    level = level.lower()
    if level == "info":
        return logging.INFO
    elif level == "critical":
        return logging.CRITICAL
    elif level == "fatal":
        return logging.FATAL
    elif level == "error":
        return logging.ERROR
    elif level == "warning" or level == "warn":
        return logging.WARNING
    elif level == "debug":
        return logging.DEBUG
    # default
    return logging.INFO

class OpaRunner:
    """
    Runs Opa in a subprocess
    """
    def __init__(self, port=OPA_PORT):
        self._port = port
        self._stopped = False
        self._process = None
        self._thread = AsyncioEventLoopThread(name="OpaRunner")
        self._on_opa_start_callbacks = []

    def start(self):
        logger.info("Launching opa runner")
        self._thread.create_task(self._run_opa_continuously())
        self._thread.start()

    def stop(self):
        logger.info("Stopping opa runner")
        self._stopped = True
        self._terminate_opa()
        time.sleep(1) # will block main thread
        self._thread.stop()

    @property
    def command(self):
        return f"opa run --server -a :{self._port}"

    def _terminate_opa(self):
        runner_logger.info("Stopping OPA")
        self._process.terminate()

    async def _run_opa_continuously(self):
        while not self._stopped:
            await self._run_opa_until_terminated()

    @retry(wait=wait_random_exponential(multiplier=0.5, max=10))
    async def _run_opa_until_terminated(self) -> int:
        """
        This function runs opa server as a subprocess.
        it returns only when the process terminates.
        """
        runner_logger.info("Running OPA", command=self.command)
        self._process = await asyncio.create_subprocess_shell(
            self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # waits a second, then runs the callbacks if process is up
        self._thread.loop.call_later(1, self._run_start_callbacks_if_process_is_up, self._process.pid)

        await asyncio.wait([
            self._log_output(self._process.stdout),
            self._log_output(self._process.stderr)
        ])

        return_code = await self._process.wait()
        runner_logger.info("OPA exited", return_code=return_code)
        if return_code > 0: # exception in running opa
            raise Exception(f"OPA exited with return code: {return_code}")
        return return_code

    def on_opa_start(self, callback: Coroutine):
        self._on_opa_start_callbacks.append(callback)

    def _run_start_callbacks_if_process_is_up(self, process_pid):
        if not psutil.pid_exists(process_pid):
            # do nothing, the process went down immediately
            return
        self._thread.create_task(self._run_start_callbacks())

    async def _run_start_callbacks(self):
        return await asyncio.gather(*(callback() for callback in self._on_opa_start_callbacks))

    async def _log_output(self, stream):
        while True:
            line = await stream.readline()
            if not line:
                break
            try:
                log_line = json.loads(line)
                msg = log_line.pop("msg", None)
                level = logging_level_from_string(log_line.pop("level", "info"))
                if msg is not None:
                    opa_logger.log(level, msg, **log_line)
                else:
                    opa_logger.log(level, line)
            except json.JSONDecodeError:
                opa_logger.info(line)

    @staticmethod
    def setup_opa_runner():
        opa_runner = OpaRunner()
        # if opa was down and restarted - its cache is clean,
        # meaning it cannot answer isAllowed queries correctly
        # in that case we rehydrate the cache.
        async def rehydrate_opa():
            runner_logger.info("Rehydrating OPA from cache")
            await opa.rehydrate_opa_from_process_cache()

        opa_runner.on_opa_start(rehydrate_opa)
        return opa_runner