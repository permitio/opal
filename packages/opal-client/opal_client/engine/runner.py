import asyncio
import os
import shutil
import signal
from abc import ABC, abstractmethod
from typing import Callable, Coroutine, List, Optional

import aiohttp
from opal_client.config import EngineLogFormat, opal_client_config
from opal_client.engine.logger import log_engine_output_opa, log_engine_output_simple
from opal_client.engine.options import CedarServerOptions, OpaServerOptions
from opal_client.logger import logger
from tenacity import retry, stop_after_attempt, wait_exponential

AsyncCallback = Callable[[], Coroutine]


class PolicyEngineRunner(ABC):
    """Runs the policy engine in a supervised subprocess.

    - if the process fails, the runner will restart the process.
    - The runner can register callbacks on the lifecycle of OPA,
    making it easy to keep the policy engine cache hydrated (up-to-date).
    - The runner can pipe the logs of the process into OPAL logger.
    """

    def __init__(
        self,
        piped_logs_format: EngineLogFormat = EngineLogFormat.NONE,
    ):
        self._stopped = False
        self._process: Optional[asyncio.subprocess.Process] = None
        self._should_stop: Optional[asyncio.Event] = None
        self._run_task: Optional[asyncio.Task] = None
        self._on_process_initial_start_callbacks: List[AsyncCallback] = []
        self._on_process_restart_callbacks: List[AsyncCallback] = []
        self._process_was_never_up_before = True
        self._piped_logs_format = piped_logs_format
        # Event that signals when the engine process is fully up **and** healthy.
        # It will be awaited by context-managers (__aenter__) so callers only
        # proceed once the underlying policy engine is ready to accept
        # requests.
        self._engine_ready: asyncio.Event = asyncio.Event()

    @abstractmethod
    def get_executable_path(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def get_arguments(self) -> list[str]:
        raise NotImplementedError()

    @abstractmethod
    async def health_check(self) -> bool:
        """Performs a health check on the policy engine.

        Returns:
            bool: True if the engine is healthy and ready to accept requests, False otherwise.
        """
        raise NotImplementedError()

    async def __aenter__(self):
        # Launch the supervised engine process.
        self.start()

        # Wait until the engine process signals it is healthy and ready.
        # The signal is set from within the runner loop once a successful
        # health-check completes.
        await self._engine_ready.wait()

        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    def start(self):
        """Starts the runner task, and launches the OPA subprocess."""
        # Make sure the ready flag is cleared before launching a fresh
        # engine instance so that callers do not receive a stale ready
        # signal from a previous run.
        self._engine_ready.clear()
        logger.info("Launching engine runner")
        self._run_task = asyncio.create_task(self._run())

    async def stop(self):
        """Stops the runner task (and terminates OPA)"""
        self._init_events()
        if not self._should_stop.is_set():
            logger.info("Stopping policy engine runner")
            self._should_stop.set()
            self._terminate_engine()
            await asyncio.sleep(1)  # wait for opa process to go down

        if self._run_task is not None:
            await self._run_task
        self._run_task = None

    async def wait_until_done(self):
        """Waits until the engine runner task is complete.

        this is great when using engine runner as a context manager.
        """
        if self._run_task is not None:
            await self._run_task

    def _terminate_engine(self):
        logger.info("Stopping policy engine")
        # Should kill group (There would be a parent shell process and a child opa process)
        os.killpg(self._process.pid, signal.SIGTERM)

    async def _run(self):
        self._init_events()
        while not self._should_stop.is_set():
            for task in asyncio.as_completed(
                [self._run_process_until_terminated(), self._should_stop.wait()]
            ):
                await task
                break

    async def pipe_logs(self):
        """Gets a stream of logs from the opa process, and logs it into the
        main opal log."""
        self._engine_panicked = False

        async def _pipe_logs_stream(stream: asyncio.StreamReader):
            line = b""
            while True:
                try:
                    line += await stream.readuntil(b"\n")
                except asyncio.exceptions.IncompleteReadError as e:
                    line += e.partial
                except asyncio.exceptions.LimitOverrunError as e:
                    # No new line yet but buffer limit exceeded, read what's available and try again
                    line += await stream.readexactly(e.consumed)
                    continue

                if not line:
                    break  # EOF, process terminated

                panic_detected = await self.handle_log_line(line)
                if not self._engine_panicked and panic_detected:
                    self._engine_panicked = True
                    # Terminate to prevent Engine from hanging,
                    # but keep streaming logs til it actually dies (for full stack trace etc.)
                    self._terminate_engine()

                line = b""

        await asyncio.gather(
            *[
                _pipe_logs_stream(self._process.stdout),
                _pipe_logs_stream(self._process.stderr),
            ]
        )
        if self._engine_panicked:
            logger.error("restart policy engine due to a detected panic")

    async def handle_log_line(self, line: bytes) -> bool:
        """Handles a single line of log from the engine process.

        returns True if the engine panicked.
        """
        raise NotImplementedError()

    @retry(wait=wait_exponential(multiplier=0.5, max=10))
    async def _run_process_until_terminated(self) -> int:
        """This function runs the policy engine as a subprocess.

        it returns only when the process terminates.
        """

        logs_sink = (
            asyncio.subprocess.DEVNULL
            if self._piped_logs_format == EngineLogFormat.NONE
            else asyncio.subprocess.PIPE
        )

        executable_path = self.get_executable_path()
        arguments = self.get_arguments()
        logger.info(
            f"Running policy engine inline: {executable_path} {' '.join(arguments)}"
        )
        self._process = await asyncio.create_subprocess_exec(
            executable_path,
            *arguments,
            stdout=logs_sink,
            stderr=logs_sink,
            start_new_session=True,
        )

        # After the process is up, we also want to make sure the
        # engine reports as healthy before we continue. We run the health
        # check in the background and set an event, so __aenter__ can await it.
        async def _set_ready_when_healthy():
            try:
                await self._wait_for_engine_health()
            except Exception as e:
                logger.error("Engine failed health check: {err}", err=e)
            else:
                self._engine_ready.set()
                # Now that the engine is confirmed healthy, run the
                # lifecycle callbacks (initial start or rehydration).
                await self._run_start_callbacks()

        asyncio.create_task(_set_ready_when_healthy())

        if self._piped_logs_format != EngineLogFormat.NONE:
            # TODO: Won't detect panic if logs aren't piped
            await self.pipe_logs()

        return_code = await self._process.wait()
        logger.info(
            f"Policy engine exited with return code: {return_code}",
        )
        if return_code > 0:  # exception in running process
            raise Exception(f"Policy engine exited with return code: {return_code}")
        return return_code

    def register_process_initial_start_callbacks(self, callbacks: List[AsyncCallback]):
        """Register a callback to run when OPA is started the first time."""
        self._on_process_initial_start_callbacks.extend(callbacks)

    def register_process_restart_callbacks(self, callbacks: List[AsyncCallback]):
        """Register a callback to run when OPA is restarted (i.e: OPA was
        already up, then got terminated, and now is up again).

        this is most often used to keep OPA's cache (policy and data)
        up-to-date, since OPA is started without policy or data. With
        empty cache, OPA cannot evaluate authorization queries
        correctly.
        """
        self._on_process_restart_callbacks.extend(callbacks)

    async def _run_start_callbacks(self):
        """Runs callbacks after OPA process starts."""
        # TODO: make policy store expose the /health api of OPA
        await asyncio.sleep(1)

        if self._process_was_never_up_before:
            # no need to rehydrate the first time
            self._process_was_never_up_before = False
            logger.info("Running policy engine initial start callbacks")
            asyncio.create_task(
                self._run_callbacks(self._on_process_initial_start_callbacks)
            )
        else:
            logger.info("Running policy engine rehydration callbacks")
            asyncio.create_task(self._run_callbacks(self._on_process_restart_callbacks))

    @retry(
        stop=stop_after_attempt(30),
        wait=wait_exponential(multiplier=0.5, min=0.1, max=2),
        reraise=True,
    )
    async def _wait_for_engine_health(self):
        """Waits for the policy engine to be healthy with exponential
        backoff."""
        logger.debug("Checking policy engine health...")
        is_healthy = await self.health_check()
        if not is_healthy:
            raise Exception("Policy engine not healthy yet")
        logger.info("Policy engine is healthy and ready")

    async def _run_callbacks(self, callbacks: List[AsyncCallback]):
        return await asyncio.gather(*(callback() for callback in callbacks))

    def _init_events(self):
        if self._should_stop is None:
            self._should_stop = asyncio.Event()


class OpaRunner(PolicyEngineRunner):
    PANIC_DETECTION_SUBSTRINGS = [b"go/src/runtime/panic.go"]

    def __init__(
        self,
        options: Optional[OpaServerOptions] = None,
        piped_logs_format: EngineLogFormat = EngineLogFormat.NONE,
    ):
        super().__init__(piped_logs_format)
        self._options = options or OpaServerOptions()

    async def handle_log_line(self, line: bytes) -> bool:
        await log_engine_output_opa(line, self._piped_logs_format)
        return any([substr in line for substr in self.PANIC_DETECTION_SUBSTRINGS])

    async def health_check(self) -> bool:
        """Performs a health check on the OPA server by calling its health
        endpoint."""
        try:
            health_url = f"{opal_client_config.POLICY_STORE_URL}/health"
            timeout_seconds = opal_client_config.POLICY_STORE_CONN_RETRY.wait_time
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                response = await session.get(health_url)
                return response.status == 200
        except Exception as e:
            logger.debug(f"OPA health check failed: {e}")
            return False

    def get_executable_path(self) -> str:
        if opal_client_config.INLINE_OPA_EXEC_PATH:
            return opal_client_config.INLINE_OPA_EXEC_PATH
        else:
            logger.warning(
                "OPA executable path not set, looking for 'opa' binary in system PATH. "
                "It is recommended to set the INLINE_OPA_EXEC_PATH configuration."
            )
            path = shutil.which("opa")
            if path is None:
                raise FileNotFoundError("OPA executable not found in PATH")
            return path

    def get_arguments(self) -> list[str]:
        args = ["run", "--server"]
        opts = self._options.get_cli_options_dict()
        args.extend(f"{k}={v}" for k, v in opts.items())
        if self._options.files:
            args.extend(self._options.files)

        return args

    @staticmethod
    def setup_opa_runner(
        options: Optional[OpaServerOptions] = None,
        piped_logs_format: EngineLogFormat = EngineLogFormat.NONE,
        initial_start_callbacks: Optional[List[AsyncCallback]] = None,
        rehydration_callbacks: Optional[List[AsyncCallback]] = None,
    ):
        """Factory for OpaRunner, accept optional callbacks to run in certain
        lifecycle events.

        Initial Start Callbacks:
            The first time we start the engine, we might want to do certain actions (like launch tasks)
            that are dependent on the policy store being up (such as PolicyUpdater, DataUpdater).

        Rehydration Callbacks:
            when the engine restarts, its cache is clean, and it does not have the state necessary
            to handle authorization queries. therefore it is necessary that we rehydrate the
            cache with fresh state fetched from the server.
        """
        opa_runner = OpaRunner(options=options, piped_logs_format=piped_logs_format)
        if initial_start_callbacks:
            opa_runner.register_process_initial_start_callbacks(initial_start_callbacks)
        if rehydration_callbacks:
            opa_runner.register_process_restart_callbacks(rehydration_callbacks)
        return opa_runner


class CedarRunner(PolicyEngineRunner):
    def __init__(
        self,
        options: Optional[CedarServerOptions] = None,
        piped_logs_format: EngineLogFormat = EngineLogFormat.NONE,
    ):
        super().__init__(piped_logs_format)
        self._options = options or CedarServerOptions()

    def get_executable_path(self) -> str:
        if opal_client_config.INLINE_CEDAR_EXEC_PATH:
            return opal_client_config.INLINE_CEDAR_EXEC_PATH
        else:
            logger.warning(
                "Cedar executable path not set, looking for 'cedar-agent' binary in system PATH. "
                "It is recommended to set the INLINE_CEDAR_EXEC_PATH configuration."
            )
            path = shutil.which("cedar-agent")
            if path is None:
                raise FileNotFoundError("Cedar agent executable not found in PATH")
            return path

    def get_arguments(self) -> list[str]:
        return list(self._options.get_args())

    async def health_check(self) -> bool:
        """Performs a health check on the Cedar agent by calling its health
        endpoint."""
        try:
            health_url = f"{opal_client_config.POLICY_STORE_URL}/health"
            timeout_seconds = opal_client_config.POLICY_STORE_CONN_RETRY.wait_time
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                response = await session.get(health_url)
                return response.status == 200
        except Exception as e:
            logger.debug(f"Cedar health check failed: {e}")
            return False

    @staticmethod
    def setup_cedar_runner(
        options: Optional[CedarServerOptions] = None,
        piped_logs_format: EngineLogFormat = EngineLogFormat.NONE,
        initial_start_callbacks: Optional[List[AsyncCallback]] = None,
        rehydration_callbacks: Optional[List[AsyncCallback]] = None,
    ):
        """Factory for CedarRunner, accept optional callbacks to run in certain
        lifecycle events.

        Initial Start Callbacks:
            The first time we start the engine, we might want to do certain actions (like launch tasks)
            that are dependent on the policy store being up (such as PolicyUpdater, DataUpdater).

        Rehydration Callbacks:
            when the engine restarts, its cache is clean and it does not have the state necessary
            to handle authorization queries. therefore it is necessary that we rehydrate the
            cache with fresh state fetched from the server.
        """
        cedar_runner = CedarRunner(options=options, piped_logs_format=piped_logs_format)

        if initial_start_callbacks:
            cedar_runner.register_process_initial_start_callbacks(
                initial_start_callbacks
            )

        if rehydration_callbacks:
            cedar_runner.register_process_restart_callbacks(rehydration_callbacks)

        return cedar_runner

    async def handle_log_line(self, line: bytes) -> bool:
        await log_engine_output_simple(line)

        return False
