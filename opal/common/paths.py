from typing import List, Set, Union
from pathlib import Path

from opal.common.utils import sorted_list_from_set

class PathUtils:
    @classmethod
    def intermediate_directories(cls, paths: List[Path]) -> List[Path]:
        """
        returns the set of all parent directories for a list of paths.
        i.e: calculate all partial paths that are directories.
        """
        directories = set()
        for path in paths:
            directories.update(path.parents)
        return sorted_list_from_set(directories)

    @classmethod
    def is_child_of_directories(cls, path: Path, directories: Set[Path]) -> bool:
        """
        whether the input path is a child of one of the input directories
        """
        return directories & set(path.parents)

    @classmethod
    def filter_children_paths_of_directories(cls, paths: List[Path], directories: Set[Path]) -> List[Path]:
        """
        returns only paths in :paths that are children of one of the paths in :directories.
        """
        return [path for path in paths if cls.is_child_of_directories(path, directories)]