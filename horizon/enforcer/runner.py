import json
import asyncio

from horizon.config import OPA_PORT
from horizon.logger import get_logger
from horizon.utils import AsyncioEventLoopThread

logger = get_logger("OPA")

class OpaRunner:
    """
    Runs Opa in a subprocess
    """
    def __init__(self, port=OPA_PORT):
        self._port = port
        self._thread = AsyncioEventLoopThread(name="OpaRunner")

    def start(self):
        self._thread.create_task(self._run_opa_continuously())
        self._thread.start()

    def stop(self):
        self._thread.stop()

    @property
    def command(self):
        return f"opa run --server -a :{self._port}"

    async def _run_opa_continuously(self):
        while True:
            logger.info("Running OPA", command=self.command)
            return_code = await self._run_opa_until_terminated()
            logger.info("OPA exited", return_code=return_code)

    async def _run_opa_until_terminated(self) -> int:
        """
        This function runs opa server as a subprocess.
        it returns only when the process terminates.
        """
        process = await asyncio.create_subprocess_exec(
            self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait([
            self._log_output(process.stdout),
            self._log_output(process.stderr)
        ])
        return await process.wait()

    async def _log_output(stream):
        while True:
            line = await stream.readline()
            if not line:
                break
            try:
                log_line = json.loads(line)
                msg = log_line.pop("msg", None)
                level = log_line.pop("level", "info")
                if msg is not None:
                    logger.log(level, msg, **log_line)
                else:
                    logger.info(log_line)
            except json.JSONDecodeError:
                logger.info(line)

opa_runner = OpaRunner()