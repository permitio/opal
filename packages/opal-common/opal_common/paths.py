from pathlib import Path
from typing import List, Set, Union

from opal_common.utils import sorted_list_from_set


class PathUtils:
    @staticmethod
    def intermediate_directories(paths: List[Path]) -> List[Path]:
        """Returns the set of all parent directories for a list of paths.

        i.e: calculate all partial paths that are directories.
        """
        directories = set()
        for path in paths:
            directories.update(path.parents)
        return sorted_list_from_set(directories)

    @staticmethod
    def is_child_of_directories(path: Path, directories: Set[Path]) -> bool:
        """Whether the input path is a child of one of the input
        directories."""
        return bool(directories & set(path.parents))

    @staticmethod
    def filter_children_paths_of_directories(
        paths: List[Path], directories: Set[Path]
    ) -> List[Path]:
        """Returns only paths in :paths that are children of one of the paths
        in :directories."""
        return [
            path
            for path in paths
            if PathUtils.is_child_of_directories(path, directories)
        ]

    @staticmethod
    def non_intersecting_directories(paths: List[Path]) -> Set[Path]:
        """Gets a list of paths (directories), and returns a set of directories
        that are non-intersecting, meaning no directory in the set is a parent
        of another directory in the set (i.e: parent directories "swallow"
        their subdirectories)."""
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

    @staticmethod
    def sort_paths_according_to_explicit_sorting(
        unsorted_paths: List[Path], explicit_sorting: List[Path]
    ) -> List[Path]:
        """The way this sorting works, is assuming that explicit_sorting does
        NOT necessarily contains all the paths found in the original list.

        We must ensure that all items in unsorted_paths must also exist
        in the output list.
        """
        unsorted = unsorted_paths.copy()

        sorted_paths: List[Path] = []
        for path in explicit_sorting:
            try:
                # we look for Path objects and not str for normalization of the path
                found_path: Path = unsorted.pop(unsorted.index(path))
                sorted_paths.append(found_path)
            except ValueError:
                continue  # skip, not found in the original list

        # add the remainder to the end of the sorted list
        sorted_paths.extend(unsorted)

        return sorted_paths

    @staticmethod
    def glob_style_match_path_to_list(path: str, match_paths: List[str]):
        """
        Check if given path matches any of the match_paths either via glob style matching or by being nested under - when the match path ends with "/**"
        return the match path if there's a match, and None otherwise
        """
        # check if any of our ignore paths match the given path
        for match_path in match_paths:
            # if the path is the root "/", then it matches any path
            if match_path == "/" or match_path == "/**":
                return match_path
            # if the path is indicated as a parent via "/**" at the end
            if match_path.endswith("/**"):
                # check if the path is under the parent
                if (path + "/").startswith((match_path[:-3] + "/")):
                    return match_path
            # otherwise check for simple (non-recursive glob matching)
            else:
                path_object = Path(path)
                if path_object.match(match_path):
                    return match_path
        # if no match - this path shouldn't be ignored
        return None
