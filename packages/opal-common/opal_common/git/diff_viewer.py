from pathlib import Path
from typing import IO, Callable, Generator, List, Optional, Set

from git import Repo
from git.diff import Diff, DiffIndex
from git.objects.commit import Commit
from opal_common.git.commit_viewer import VersionedFile
from opal_common.paths import PathUtils

DiffFilter = Callable[[Diff], bool]
PathFilter = Callable[[Path], bool]


def apply_filter(
    generator: Generator[Diff, None, None], filter: Optional[DiffFilter] = None
) -> Generator[Diff, None, None]:
    """applies an optional filter on top of a Diff generator.

    returns only the diffs yielded by the source generator that pass the
    filter. if no filter is provided, returns the same results as the
    source generator.
    """
    if filter is None:
        yield from generator
    else:
        for diff in generator:
            if filter(diff):
                yield diff


def diffed_file_has_extension(
    diff: Diff, extensions: Optional[List[str]] = None
) -> bool:
    """filter on git diffs, filters only diffs on files that has a certain
    extension/type.

    if the file is renamed/added/removed, its enough that only one of
    its versions has the required extension.
    """
    if extensions is None:
        return True  # no filter

    for path in [diff.a_path, diff.b_path]:
        if path is not None and Path(path).suffix in extensions:
            return True
    return False


def diffed_file_is_under_directories(diff: Diff, directories: Set[Path]) -> bool:
    """filter on git diffs, filters only diffs on files that are located in
    certain directories.

    if a file is renamed/added/removed, its enough that only one of its
    versions was located in one of the required directories.
    """
    for path in [diff.a_path, diff.b_path]:
        if path is not None and PathUtils.is_child_of_directories(
            Path(path), directories
        ):
            return True
    return False


class DiffViewer:
    """This class allows us to view the changes made between two commits.

    these two commits are not necessarily consecutive.
    """

    def __init__(self, old: Commit, new: Commit):
        """[summary]

        Args:
            old (Commit): the older/earlier commit that defines the diff
            new (Commit): the newer/later commit that defines the diff
        """
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

    def changes(
        self, filter: Optional[DiffFilter] = None
    ) -> Generator[Diff, None, None]:
        """a generator yielding all the diffs between the old commit and the
        new commit, after applying the filter.

        Each diff (instance of `Diff`) is a change in one file, i.e: if the
        diff between the commits returned by git diff is as following:

        Changes to be committed:
        (use "git restore --staged <file>..." to unstage)
            modified:   server/main.py
            deleted:    server/policy/publisher.py
            new file:   server/publisher.py

        then 3 Diffs will be returned (one modified, one deleted, one added).

        Args:
            filter (Optional[DiffFilter]): an optional predicate to filter only specific diffs.

        Yields:
            the next diff found (only for diffs passing the filter).
        """
        for diff in self._diffs:
            if filter is None:
                yield diff
            elif filter(diff):
                yield diff

    def added(self, filter: Optional[DiffFilter] = None) -> Generator[Diff, None, None]:
        """a generator yielding all the diffs between the old commit and the
        new commit, that are of type "new file" (i.e: added), after applying
        the filter.

        @see `changes()`
        """
        diff_generator = self._diffs.iter_change_type("A")
        yield from apply_filter(diff_generator, filter)

    def deleted(
        self, filter: Optional[DiffFilter] = None
    ) -> Generator[Diff, None, None]:
        """a generator yielding all the diffs between the old commit and the
        new commit, that are of type "deleted", after applying the filter.

        @see `changes()`
        """
        diff_generator = self._diffs.iter_change_type("D")
        yield from apply_filter(diff_generator, filter)

    def renamed(
        self, filter: Optional[DiffFilter] = None
    ) -> Generator[Diff, None, None]:
        """a generator yielding all the diffs between the old commit and the
        new commit, that are of type "renamed", after applying the filter.

        @see `changes()`
        """
        diff_generator = self._diffs.iter_change_type("R")
        yield from apply_filter(diff_generator, filter)

    def modified(
        self, filter: Optional[DiffFilter] = None
    ) -> Generator[Diff, None, None]:
        """a generator yielding all the diffs between the old commit and the
        new commit, that are of type "modified", after applying the filter.

        @see `changes()`
        """
        diff_generator = self._diffs.iter_change_type("M")
        yield from apply_filter(diff_generator, filter)

    def added_files(
        self, filter: Optional[DiffFilter] = None
    ) -> Generator[VersionedFile, None, None]:
        """a generator yielding the new version (blob) of files that were added
        (or renamed, meaning a new file was added under the new name) in the
        diff, between the old and new commits.

        In both cases, a new file that has not existed before was added
        to the repo.
        """
        for diff in self.added(filter):
            yield VersionedFile(diff.b_blob, self._new)

        for diff in self.renamed(filter):
            yield VersionedFile(diff.b_blob, self._new)

    def deleted_files(
        self, filter: Optional[DiffFilter] = None
    ) -> Generator[VersionedFile, None, None]:
        """a generator yielding the old version (blob) of the files that were
        removed (or renamed, meaning the file under the old name was removed)
        in the diff between the old and new commits.

        In both cases, a file is removed from the repo.
        """
        for diff in self.deleted(filter):
            yield VersionedFile(diff.a_blob, self._old)

        for diff in self.renamed(filter):
            yield VersionedFile(diff.a_blob, self._old)

    def modified_files(
        self, filter: Optional[DiffFilter] = None
    ) -> Generator[VersionedFile, None, None]:
        """a generator yielding the new version (blob) of files that were
        changed (modified) in the diff between the old and new commit."""
        for diff in self.modified(filter):
            yield VersionedFile(diff.b_blob, self._new)

    def added_or_modified_files(
        self, filter: Optional[DiffFilter] = None
    ) -> Generator[VersionedFile, None, None]:
        """a shortcut generator yield both `added_files()` and
        `modified_files()`."""
        yield from self.added_files(filter)
        yield from self.modified_files(filter)

    def affected_paths(self, filter: Optional[PathFilter] = None) -> Set[Path]:
        """returns the set of paths of all files that were affected in the diff
        between the old and new commits.

        only file paths are returned (and not directories).
        """
        paths = set()
        for diff in self._diffs:
            diff: Diff
            for str_path in [diff.a_path, diff.b_path]:
                if str_path is not None:
                    path = Path(str_path)
                    if filter is None:
                        paths.add(path)
                    elif filter(path):
                        paths.add(path)
        return paths
