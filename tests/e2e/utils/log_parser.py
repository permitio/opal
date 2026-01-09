import re
from typing import List, Optional, Dict


class LogParser:
    """Utility for parsing and analyzing Docker container logs."""

    def __init__(self, docker_manager, container_name: str):
        """
        Initialize log parser.

        Args:
            docker_manager: DockerManager instance
            container_name: Name of the container to parse logs from
        """
        self.docker_manager = docker_manager
        self.container_name = container_name
        self._cached_logs = None

    def get_all(self, refresh: bool = True) -> str:
        """
        Get all logs from container.

        Args:
            refresh: Whether to fetch fresh logs from container

        Returns:
            All container logs as string
        """
        if refresh or self._cached_logs is None:
            self._cached_logs = self.docker_manager.get_logs(self.container_name)
        return self._cached_logs

    def get_latest(self, lines: int = 100, refresh: bool = True) -> str:
        """
        Get last N lines of logs.

        Args:
            lines: Number of lines to retrieve
            refresh: Whether to fetch fresh logs

        Returns:
            Last N lines of logs
        """
        all_logs = self.get_all(refresh=refresh)
        log_lines = all_logs.split('\n')
        return '\n'.join(log_lines[-lines:])

    def filter_by_level(self, level: str, case_sensitive: bool = False) -> List[str]:
        """
        Filter log lines by log level.

        Args:
            level: Log level to filter (ERROR, CRITICAL, WARNING, INFO, DEBUG)
            case_sensitive: Whether to perform case-sensitive matching

        Returns:
            List of log lines matching the level
        """
        logs = self.get_all(refresh=True)

        if case_sensitive:
            pattern = re.compile(rf".*\b{level}\b.*")
        else:
            pattern = re.compile(rf".*\b{level}\b.*", re.IGNORECASE)

        return [line for line in logs.split('\n') if pattern.match(line) and line.strip()]

    def search(self, pattern: str, regex: bool = False, case_sensitive: bool = False) -> List[str]:
        """
        Search for pattern in logs.

        Args:
            pattern: Pattern to search for
            regex: Whether pattern is a regular expression
            case_sensitive: Whether to perform case-sensitive search

        Returns:
            List of log lines matching the pattern
        """
        logs = self.get_all(refresh=True)

        if regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled = re.compile(pattern, flags)
            return [line for line in logs.split('\n') if compiled.search(line) and line.strip()]
        else:
            if case_sensitive:
                return [line for line in logs.split('\n') if pattern in line and line.strip()]
            else:
                pattern_lower = pattern.lower()
                return [line for line in logs.split('\n') if pattern_lower in line.lower() and line.strip()]

    def count_occurrences(self, pattern: str, regex: bool = False, case_sensitive: bool = False) -> int:
        """
        Count occurrences of pattern in logs.

        Args:
            pattern: Pattern to count
            regex: Whether pattern is a regular expression
            case_sensitive: Whether to perform case-sensitive search

        Returns:
            Number of occurrences
        """
        return len(self.search(pattern, regex=regex, case_sensitive=case_sensitive))

    def has_pattern(self, pattern: str, regex: bool = False, case_sensitive: bool = False) -> bool:
        """
        Check if pattern exists in logs.

        Args:
            pattern: Pattern to search for
            regex: Whether pattern is a regular expression
            case_sensitive: Whether to perform case-sensitive search

        Returns:
            True if pattern found, False otherwise
        """
        return self.count_occurrences(pattern, regex=regex, case_sensitive=case_sensitive) > 0

    def get_errors_and_critical(self) -> Dict[str, List[str]]:
        """
        Get all ERROR and CRITICAL level log lines.

        Returns:
            Dictionary with 'errors' and 'critical' keys containing matching lines
        """
        return {
            'errors': self.filter_by_level('ERROR'),
            'critical': self.filter_by_level('CRITICAL')
        }
