import asyncio
import time
from typing import Callable, Coroutine, List, Optional

import psutil
from opal_client.config import OpaLogFormat
from opal_client.logger import logger
from opal_client.opa.logger import pipe_opa_logs
from opal_client.opa.options import OpaServerOptions
from tenacity import retry, wait_random_exponential

AsyncCallback = Callable[[], Coroutine]


async def wait_until_process_is_up(
    process_pid: int,
    callback: Optional[AsyncCallback],
    wait_interval: float = 0.1,
    timeout: Optional[float] = None,
):
    """waits until the pid of the process exists, then optionally runs a
    callback.

    optionally receives a timeout to give up.
    """
    start_time = time.time()
    while not psutil.pid_exists(process_pid):
        if timeout is not None and start_time - time() > timeout:
            break
        await asyncio.sleep(wait_interval)
    if callback is not None:
        await callback()


class OpaRunner:
    """Runs OPA in a supervised subprocess.

    - if the OPA process fails, OPA runner will restart the process.
    - OPA runner can register callbacks on the lifecycle of OPA,
    making it easy to keep the OPA cache hydrated (up-to-date).
    - OPA runner can pipe the logs of the OPA process into OPAL logger.
    """

    def __init__(
        self,
        options: Optional[OpaServerOptions] = None,
        piped_logs_format: OpaLogFormat = OpaLogFormat.NONE,
    ):
        self._options = options or OpaServerOptions()
        self._stopped = False
        self._process = None
        self._should_stop: Optional[asyncio.Event] = None
        self._run_task: Optional[asyncio.Task] = None
        self._on_opa_initial_start_callbacks: List[AsyncCallback] = []
        self._on_opa_restart_callbacks: List[AsyncCallback] = []
        self._process_was_never_up_before = True
        self._piped_logs_format = piped_logs_format

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    def start(self):
        """starts the opa runner task, and launches the OPA subprocess."""
        logger.info("Launching opa runner")
        self._run_task = asyncio.create_task(self._run())

    async def stop(self):
        """stops the opa runner task (and terminates OPA)"""
        self._init_events()
        if not self._should_stop.is_set():
            logger.info("Stopping opa runner")
            self._should_stop.set()
            self._terminate_opa()
            await asyncio.sleep(1)  # wait for opa process to go down

        if self._run_task is not None:
            await self._run_task
        self._run_task = None

    async def wait_until_done(self):
        """waits until the OPA runner task is complete.

        this is great when using opa runner as a context manager.
        """
        if self._run_task is not None:
            await self._run_task

    @property
    def command(self):
        opts = self._options.get_cli_options_dict()
        opts_string = " ".join([f"{k}={v}" for k, v in opts.items()])
        startup_files = self._options.get_opa_startup_files()
        return f"opa run --server {opts_string} {startup_files}".strip()

    def _terminate_opa(self):
        logger.info("Stopping OPA")
        self._process.terminate()

    async def _run(self):
        self._init_events()
        while not self._should_stop.is_set():
            for task in asyncio.as_completed(
                [self._run_opa_until_terminated(), self._should_stop.wait()]
            ):
                await task
                break

    @retry(wait=wait_random_exponential(multiplier=0.5, max=10))
    async def _run_opa_until_terminated(self) -> int:
        """This function runs opa server as a subprocess.

        it returns only when the process terminates.
        """
        logger.info("Running OPA inline: {command}", command=self.command)

        logs_sink = (
            asyncio.subprocess.DEVNULL
            if self._piped_logs_format == OpaLogFormat.NONE
            else asyncio.subprocess.PIPE
        )

        self._process = await asyncio.create_subprocess_shell(
            self.command,
            stdout=logs_sink,
            stderr=logs_sink,
            start_new_session=True,
        )

        # waits until the process is up, then runs a callback
        asyncio.create_task(
            wait_until_process_is_up(
                self._process.pid, callback=self._run_start_callbacks
            )
        )

        if self._piped_logs_format != OpaLogFormat.NONE:
            await asyncio.wait(
                [
                    pipe_opa_logs(self._process.stdout, self._piped_logs_format),
                    pipe_opa_logs(self._process.stderr, self._piped_logs_format),
                ]
            )

        return_code = await self._process.wait()
        logger.info(
            "OPA exited with return code: {return_code}", return_code=return_code
        )
        if return_code > 0:  # exception in running opa
            raise Exception(f"OPA exited with return code: {return_code}")
        return return_code

    def register_opa_initial_start_callbacks(self, callbacks: List[AsyncCallback]):
        """register a callback to run when OPA is started the first time."""
        self._on_opa_initial_start_callbacks.extend(callbacks)

    def register_opa_restart_callbacks(self, callbacks: List[AsyncCallback]):
        """register a callback to run when OPA is restarted (i.e: OPA was
        already up, then got terminated, and now is up again).

        this is most often used to keep OPA's cache (policy and data)
        up-to-date, since OPA is started without policy or data. With
        empty cache, OPA cannot evaluate authorization queries
        correctly.
        """
        self._on_opa_restart_callbacks.extend(callbacks)

    async def _run_start_callbacks(self):
        """runs callbacks after OPA process starts."""
        # TODO: make policy store expose the /health api of OPA
        await asyncio.sleep(1)

        if self._process_was_never_up_before:
            # no need to rehydrate the first time
            self._process_was_never_up_before = False
            logger.info("Running OPA initial start callbacks")
            asyncio.create_task(
                self._run_callbacks(self._on_opa_initial_start_callbacks)
            )
        else:
            logger.info("Running OPA rehydration callbacks")
            asyncio.create_task(self._run_callbacks(self._on_opa_restart_callbacks))

    async def _run_callbacks(self, callbacks: List[AsyncCallback]):
        return await asyncio.gather(*(callback() for callback in callbacks))

    def _init_events(self):
        if self._should_stop is None:
            self._should_stop = asyncio.Event()

    @staticmethod
    def setup_opa_runner(
        options: Optional[OpaServerOptions] = None,
        piped_logs_format: OpaLogFormat = OpaLogFormat.NONE,
        initial_start_callbacks: Optional[List[AsyncCallback]] = None,
        rehydration_callbacks: Optional[List[AsyncCallback]] = None,
    ):
        """factory for OpaRunner, accept optional callbacks to run in certain
        lifecycle events.

        Initial Start Callbacks:
            The first time we start opa, we might want to do certain actions (like launch tasks)
            that are dependant on the policy store being up (such as PolicyUpdater, DataUpdater).

        Rehydration Callbacks:
            when opa restarts, its cache is clean and it does not have the state necessary
            to handle authorization queries. therefore it is necessary that we rehydrate the
            cache with fresh state fetched from the server.
        """
        opa_runner = OpaRunner(options=options, piped_logs_format=piped_logs_format)
        if initial_start_callbacks:
            opa_runner.register_opa_initial_start_callbacks(initial_start_callbacks)
        if rehydration_callbacks:
            opa_runner.register_opa_restart_callbacks(rehydration_callbacks)
        return opa_runner
