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
    ):
        log_found = False
        logs = self._container.logs(stream=True)
        start_time = time.time()

        for line in logs:
            if time.time() - start_time > timeout:
                self.opalLogger.warning(
                    f"{self.settings.container_name} | Timeout reached while waiting for the log. | {log_str}"
                )
                break

            decoded_line = line.decode("utf-8").strip()
            match = re.search(self.timestamp_with_ansi, decoded_line)
            if match:
                log_timestamp_string = match.group(1)
                log_timestamp = datetime.strptime(
                    log_timestamp_string, "%Y-%m-%dT%H:%M:%S.%f%z"
                )

                if (reference_timestamp is None) or (
                    log_timestamp > reference_timestamp
                ):
                    if log_str in decoded_line:
                        log_found = True
                        break

        return log_found
