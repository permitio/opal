from typing import List


class ModuleFilter:
    """filter logs by module name."""

    def __init__(
        self, exclude_list: List[str] = None, include_list: List[str] = None
    ) -> None:
        """[summary]

        Args:
            exclude_list (List[str], optional): module name (prefixes) to reject. Defaults to [].
            include_list (List[str], optional): module name (prefixes) to include (even if higher form is excluded). Defaults to [].

        Usage:
            ModuleFilter(["uvicorn"]) # exclude all logs coming from module name starting with "uvicorn"
            ModuleFilter(["uvicorn"], ["uvicorn.access]) # exclude all logs coming from module name starting with "uvicorn" except ones starting with "uvicorn.access")
        """
        self._exclude_list = exclude_list or []
        self._include_list = include_list or []

    def filter(self, record):
        name: str = record["name"]
        for module in self._include_list:
            if name.startswith(module):
                return True
        for module in self._exclude_list:
            if name.startswith(module):
                return False
        return True
