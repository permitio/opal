from typing import IO, Generator, Callable, Optional, List, Set
from pathlib import Path

from git import Repo
from git.diff import DiffIndex, Diff
from git.objects.commit import Commit

from opal.common.git.commit_viewer import VersionedFile
from opal.common.paths import PathUtils

DiffFilter = Callable[[Diff], bool]
PathFilter = Callable[[Path], bool]

def apply_filter(
    generator: Generator[Diff, None, None],
    filter: Optional[DiffFilter] = None
) -> Generator[Diff, None, None]:
    if filter is None:
        yield from generator
    else:
        for diff in generator:
            if filter(diff):
                yield diff

def diffed_file_has_extension(diff: Diff, extensions: Optional[List[str]] = None) -> bool:
    if extensions is None:
        return True # no filter

    for path in [diff.a_path, diff.b_path]:
        if path is not None and Path(path).suffix in extensions:
            return True
    return False

def diffed_file_is_under_directories(diff: Diff, directories: Set[Path]) -> bool:
    for path in [diff.a_path, diff.b_path]:
        if path is not None and PathUtils.is_child_of_directories(Path(path), directories):
            return True
    return False

class DiffViewer:
    """
    This class allows us to view the changes made between two commits. these
    two commits are not necessarily consecutive.

    The viewer also allows us to filter out paths of the commit tree.
    """
    def __init__(self, old: Commit, new: Commit):
        if old.repo != new.repo:
            raise ValueError("you can only diff two commits from the same repo!")
        self._repo: Repo = old.repo
        self._old = old
        self._new = new
        self._diffs: DiffIndex = old.diff(new)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def changes(self, filter: Optional[DiffFilter] = None) -> Generator[Diff, None, None]:
        for diff in self._diffs:
            if filter is None:
                yield diff
            elif filter(diff):
                yield diff

    def added(self, filter: Optional[DiffFilter] = None) -> Generator[Diff, None, None]:
        diff_generator = self._diffs.iter_change_type("A")
        yield from apply_filter(diff_generator, filter)

    def deleted(self, filter: Optional[DiffFilter] = None) -> Generator[Diff, None, None]:
        diff_generator = self._diffs.iter_change_type("D")
        yield from apply_filter(diff_generator, filter)

    def renamed(self, filter: Optional[DiffFilter] = None) -> Generator[Diff, None, None]:
        diff_generator = self._diffs.iter_change_type("R")
        yield from apply_filter(diff_generator, filter)

    def modified(self, filter: Optional[DiffFilter] = None) -> Generator[Diff, None, None]:
        diff_generator = self._diffs.iter_change_type("M")
        yield from apply_filter(diff_generator, filter)


    def added_files(self, filter: Optional[DiffFilter] = None) -> Generator[VersionedFile, None, None]:
        """
        returns the versioned files (blobs) of the files that were added or renamed in the diff.
        in both cases, a new file that has not existed before was added to the repo.
        since the new state is what interesting, we return the b_blob (which represents the new state).
        """
        for diff in self.added(filter):
            yield VersionedFile(diff.b_blob, self._new)

        for diff in self.renamed(filter):
            yield VersionedFile(diff.b_blob, self._new)

    def deleted_files(self, filter: Optional[DiffFilter] = None) -> Generator[VersionedFile, None, None]:
        """
        returns the old version (blob) of the files that were
        removed (or renamed -> old name removed) in the diff.
        in both cases, a file is removed from the repo.
        since the new state has no blob we return the old blob.
        """
        for diff in self.deleted(filter):
            yield VersionedFile(diff.a_blob, self._old)

        for diff in self.renamed(filter):
            yield VersionedFile(diff.a_blob, self._old)

    def modified_files(self, filter: Optional[DiffFilter] = None) -> Generator[VersionedFile, None, None]:
        """
        returns the new version (blob) of files that were changed in the diff.
        """
        for diff in self.modified(filter):
            yield VersionedFile(diff.b_blob, self._new)

    def added_or_modified_files(self, filter: Optional[DiffFilter] = None) -> Generator[VersionedFile, None, None]:
        yield from self.added_files(filter)
        yield from self.modified_files(filter)

    def affected_paths(self, filter: Optional[PathFilter] = None) -> Set[Path]:
        paths = set()
        for diff in self._diffs:
            diff: Diff
            for str_path in [diff.a_path, diff.b_path]:
                if str_path is not None:
                    path = Path(str_path)
                    if filter(path):
                        paths.add(path)
        return paths
