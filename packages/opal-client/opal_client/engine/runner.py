import asyncio
import os
import shutil
import signal
import time
from abc import ABC, abstractmethod
from typing import Callable, Coroutine, List, Optional

import psutil
from opal_client.config import EngineLogFormat, opal_client_config
from opal_client.engine.logger import log_engine_output_opa, log_engine_output_simple
from opal_client.engine.options import CedarServerOptions, OpaServerOptions
from opal_client.logger import logger
from tenacity import retry, wait_random_exponential

AsyncCallback = Callable[[], Coroutine]


async def wait_until_process_is_up(
    process_pid: int,
    callback: Optional[AsyncCallback],
    wait_interval: float = 0.1,
    timeout: Optional[float] = None,
):
    """Waits until the pid of the process exists, then optionally runs a
    callback.

    optionally receives a timeout to give up.
    """
    start_time = time.time()
    while not psutil.pid_exists(process_pid):
        if timeout is not None and start_time - time.time() > timeout:
            break
        await asyncio.sleep(wait_interval)
    if callback is not None:
        await callback()


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

    @abstractmethod
    def get_executable_path(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def get_arguments(self) -> list[str]:
        raise NotImplementedError()

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    def start(self):
        """Starts the runner task, and launches the OPA subprocess."""
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

    @retry(wait=wait_random_exponential(multiplier=0.5, max=10))
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

        # waits until the process is up, then runs a callback
        asyncio.create_task(
            wait_until_process_is_up(
                self._process.pid, callback=self._run_start_callbacks
            )
        )

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
