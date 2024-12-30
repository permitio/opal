import re
import time
from datetime import datetime
from testcontainers.core.utils import setup_logger


class PermitContainer():
    def __init__(self):
        self.permitLogger = setup_logger(__name__)

        # Regex to match any ANSI-escaped timestamp in the format YYYY-MM-DDTHH:MM:SS.mmmmmm+0000
        self.timestamp_with_ansi = r"\x1b\[.*?(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+\d{4})"
        self.errors = []
        self.check_errors()


    def wait_for_log(self, reference_timestamp: datetime, log_str: str, timeout: int):
        """
        Wait for a specific log to appear in the container logs after the reference timestamp.
        
        Args:
            reference_timestamp (datetime): The timestamp to start checking logs from.
            log_str (str): The string to search for in the logs.
            timeout (int): Maximum time to wait for the log (in seconds).
            
        Returns:
            bool: True if the log was found, False if the timeout was reached.
        """
        # Stream logs from the opal_client container
        log_found = False
        logs = self._container.logs(stream=True)

        self.permitLogger.info("Streaming container logs...")

        start_time = time.time()  # Record the start time

        for line in logs:
            # Check if the timeout has been exceeded
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                self.permitLogger.warning("Timeout reached while waiting for the log.")
                break

            decoded_line = line.decode("utf-8").strip()

            # Search for the timestamp in the line
            match = re.search(self.timestamp_with_ansi, decoded_line)
            if match:
                log_timestamp_string = match.group(1)
                log_timestamp = datetime.strptime(log_timestamp_string, "%Y-%m-%dT%H:%M:%S.%f%z")
                
                if log_timestamp > reference_timestamp:
                    self.permitLogger.info(f"Checking log line: {decoded_line}")
                    if log_str in decoded_line:
                        log_found = True
                        self.permitLogger.info("Log found!")
                        break

        return log_found

    def wait_for_error(self, reference_timestamp: datetime, error_str: str = "Error", timeout: int = 30):
        """
        Wait for a specific log to appear in the container logs after the reference timestamp.
        
        Args:
            reference_timestamp (datetime): The timestamp to start checking logs from.
            log_str (str): The string to search for in the logs.
            timeout (int): Maximum time to wait for the log (in seconds).
            
        Returns:
            bool: True if the log was found, False if the timeout was reached.
        """
        # Stream logs from the opal_client container
        err_found = False
        logs = self._container.logs(stream=True)

        self.permitLogger.info("Streaming container logs...")

        start_time = time.time()  # Record the start time

        for line in logs:
            # Check if the timeout has been exceeded
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                self.permitLogger.warning("Timeout reached while waiting for the log.")
                break

            decoded_line = line.decode("utf-8").strip()

            # Search for the timestamp in the line
            match = re.search(self.timestamp_with_ansi, decoded_line)
            if match:
                log_timestamp_string = match.group(1)
                log_timestamp = datetime.strptime(log_timestamp_string, "%Y-%m-%dT%H:%M:%S.%f%z")
                
                if log_timestamp > reference_timestamp:
                    self.permitLogger.info(f"Checking log line: {decoded_line}")
                    if error_str in decoded_line:
                        err_found = True
                        for err in self.errors:
                            m = re.search(self.timestamp_with_ansi, decoded_line)
                            if m.group(1) == match.group(1):
                                self.errors.remove(err)
                        self.permitLogger.info("err found!")
                        break
        return err_found


    async def check_errors(self):
        # Stream logs from the opal_client container
        logs = self._container.logs(stream=True)

        log_str = "ERROR"

        self.permitLogger.info("Streaming container logs...")
        for line in logs:
            decoded_line = line.decode("utf-8").strip()
            self.permitLogger.info(f"Checking log line: {decoded_line}")
            self.permitLogger.info(f"scanning line: {decoded_line}")
            if log_str in decoded_line:
                self.permitLogger.error("\n\n\n\n")
                self.permitLogger.error(f"error found: {decoded_line}")
                self.permitLogger.error("\n\n\n\n")
                self.errors.append(decoded_line)

    def __del__(self):
        if len(self.errors) > 0:
            self.permitLogger.error("Errors found in container logs:")
            for error in self.errors:
                self.permitLogger.error(error)
            assert False, "Errors found in container logs."
