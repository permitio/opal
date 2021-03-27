from typing import List, Set, Union
from pathlib import Path

from opal_common.utils import sorted_list_from_set

class PathUtils:
    @staticmethod
    def intermediate_directories(paths: List[Path]) -> List[Path]:
        """
        returns the set of all parent directories for a list of paths.
        i.e: calculate all partial paths that are directories.
        """
        directories = set()
        for path in paths:
            directories.update(path.parents)
        return sorted_list_from_set(directories)

    @staticmethod
    def is_child_of_directories(path: Path, directories: Set[Path]) -> bool:
        """
        whether the input path is a child of one of the input directories
        """
        return bool(directories & set(path.parents))

    @staticmethod
    def filter_children_paths_of_directories(paths: List[Path], directories: Set[Path]) -> List[Path]:
        """
        returns only paths in :paths that are children of one of the paths in :directories.
        """
        return [path for path in paths if PathUtils.is_child_of_directories(path, directories)]

    @staticmethod
    def non_intersecting_directories(paths: List[Path]) -> Set[Path]:
        """
        gets a list of paths (directories), and returns a set of directories that are non-intersecting,
        meaning no directory in the set is a parent of another directory in the set (i.e: parent
        directories "swallow" their subdirectories).
        """
        output_paths = set()
        for candidate in paths:
            if set(candidate.parents) & output_paths:
                # the next candidate is covered by a parent which is already in output -> SKIP
                # or the next candidate is already in the list
                continue
            for out_path in list(output_paths):
                # the next candidate can displace a child from the output
                if candidate in list(out_path.parents):
                    output_paths.remove(out_path)
            output_paths.add(candidate)
        return output_paths