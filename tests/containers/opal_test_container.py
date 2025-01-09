import threading
import asyncio
import re
import time
from datetime import datetime

from testcontainers.core.utils import setup_logger


class OpalTestContainer:
    def __init__(self, **kwargs):
        self.opalLogger = setup_logger(__name__)

        # Add custom labels to the kwargs
        labels = kwargs.get("labels", {})
        labels.update({"com.docker.compose.project": "pytest"})
        kwargs["labels"] = labels

        self.timestamp_with_ansi = (
            r"\x1b\[.*?(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+\d{4})"
        )


    def wait_for_log(
        self, log_str: str, timeout: int, reference_timestamp: datetime | None = None
    ) -> bool:
        """
        Wait for a specific log to appear in the container logs after the
        reference timestamp.

        Args:
            log_str (str): The string to search for in the logs.
            timeout (int): Maximum time to wait for the log (in seconds).
            reference_timestamp (datetime | None): The timestamp to start checking logs from.

        Returns:
            bool: True if the log was found, False if the timeout was reached.
        """

        #timeout = 0.1
        timeout = timeout

        log_found = threading.Event()

        def process_logs():
            """
            Asynchronous sub-function to check logs with timeout handling.
            """
            #input(f"Press Enter to continue... searching for: {log_str} | on container: {self.settings.container_name} | timeout set to: {timeout}")
            logs = self._container.logs(stream=True)  # Stream logs
            start_time = time.time()

            for line in logs:  # Synchronous iteration over logs
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout:
                    self.opalLogger.warning(
                        f"{self.settings.container_name} | Timeout reached while waiting for the log. | {log_str}"
                    )
                    break

                decoded_line = line.decode("utf-8").strip()

                # Extract timestamp if present
                match = re.search(self.timestamp_with_ansi, decoded_line)
                if match:
                    log_timestamp_string = match.group(1)
                    log_timestamp = datetime.strptime(
                        log_timestamp_string, "%Y-%m-%dT%H:%M:%S.%f%z"
                    )

                    if reference_timestamp is None or log_timestamp > reference_timestamp:
                        if log_str in decoded_line:
                            log_found.set()  # Signal that the log was found
                            break
        
        log_thread = threading.Thread(target=process_logs)
        log_thread.start()

        log_thread.join(timeout=float(timeout))

        if not log_found.is_set():
            self.opalLogger.warning(
                f"{self.settings.container_name} | Timeout reached while waiting for the log. | {log_str}"
            )
            return False

        return True
    