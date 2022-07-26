from pathlib import Path
from typing import IO, Callable, Generator, List, Optional, Set

from git import Repo
from git.objects import Blob, Commit, IndexObject, Tree
from opal_common.paths import PathUtils


class VersionedNode:
    """A *versioned* file or a directory in a git repo.

    VersionedNode is a base class for `VersionedFile` and
    `VersionedDirectory`.
    """

    def __init__(self, node: IndexObject, commit: Commit):
        self._node = node
        self._commit = commit
        self._repo: Repo = commit.repo

    @property
    def repo(self) -> Repo:
        """the repo containing the versioned node."""
        return self._repo

    @property
    def commit(self) -> Commit:
        """the commit in which the node (blob, tree) is located."""
        return self._commit

    @property
    def version(self) -> str:
        """the hash (hex sha) of the node's parent commit."""
        return self._commit.hexsha

    @property
    def path(self) -> Path:
        """the relative path to the node (either file path or directory path),
        relative to the repo root."""
        return Path(self._node.path)


class VersionedFile(VersionedNode):
    """Each instance of this class represents *one version* of a file (blob) in
    a git repo (the version of the file for a specific git commit)."""

    def __init__(self, blob: Blob, commit: Commit):
        super().__init__(blob, commit)
        self._blob: Blob = blob

    @property
    def blob(self) -> Blob:
        """the blob containing metadata for the file version."""
        return self._blob

    @property
    def stream(self) -> IO:
        """an io stream to the version of the file represented by that
        instance.

        reading that stream will return the contents of the file for
        that specific version (commit).
        """
        return self.blob.data_stream

    def read_bytes(self) -> bytes:
        """returns the contents of the file as a byte array (without
        encoding)."""
        return self.stream.read()

    def read(self, encoding="utf-8") -> str:
        """returns the contents of the file as a string, decoded according to
        the input `encoding`.

        (by default, git usually encodes source files as utf-8).
        """
        return self.read_bytes().decode(encoding=encoding)


class VersionedDirectory(VersionedNode):
    """Each instance of this class represents *one version* of a directory (git
    tree) in a git repo (the version of the directory for a specific git
    commit)."""

    def __init__(self, directory: Tree, commit: Commit):
        super().__init__(directory, commit)
        self._dir: Tree = directory

    @property
    def dir(self) -> Tree:
        """the git tree representing the metadata for that version of the
        directory.

        i.e: one can get child directories (trees) and files (blobs) for the instance's version.
        """
        return self._dir


NodeFilter = Callable[[VersionedNode], bool]
FileFilter = Callable[[VersionedFile], bool]
DirectoryFilter = Callable[[VersionedDirectory], bool]


def has_extension(f: VersionedFile, extensions: Optional[List[str]] = None) -> bool:
    """a filter on versioned files, filters only files with specific types
    (file extensions)."""
    if extensions is None:
        return True  # no filter
    else:
        return f.path.suffix in extensions


def is_under_directories(f: VersionedFile, directories: Set[Path]) -> bool:
    """a filter on versioned files, filters only files under certain
    directories in the repo."""
    return PathUtils.is_child_of_directories(f.path, directories)


class CommitViewer:
    """This class allows us to view the repository files and directories from
    the perspective of a specific git commit (i.e: version).

    i.e: if in the latest commit we removed a file called `a.txt`, we will
    see it while initializing CommitViewer with commit=HEAD~1, but we will
    not see `a.txt` if we initialize the CommitViewer with commit=HEAD.

    The viewer also allows us to filter out certain paths of the commit tree.
    """

    def __init__(self, commit: Commit):
        """[summary]

        Args:
            commit (Commit): the commit that defines the perspective (or lens)
                through which we look at the repo filesystem. i.e: the commit
                that defines the "checkout".
        """
        self._repo: Repo = commit.repo
        self._commit = commit
        self._root = commit.tree

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def nodes(
        self, predicate: Optional[NodeFilter] = None
    ) -> Generator[VersionedNode, None, None]:
        """a generator yielding all the nodes (files and directories) found in
        the repository for the current commit, after applying the filter.

        Args:
            predicate (Optional[NodeFilter]): an optional predicate to filter only specific nodes.

        Yields:
            the next node found (only for nodes passing the filter).
        """
        nodes_generator = self._nodes_in_tree(self._root)
        if predicate is None:
            return nodes_generator
        else:
            return filter(predicate, nodes_generator)

    def files(
        self, predicate: Optional[FileFilter] = None
    ) -> Generator[VersionedFile, None, None]:
        """a generator yielding all the files found in the repository for the
        current commit, after applying the filter.

        Args:
            filter (Optional[FileFilter]): an optional predicate to filter only specific files.

        Yields:
            the next file found (only for files passing the filter).
        """
        return (
            node for node in self.nodes(predicate) if isinstance(node, VersionedFile)
        )

    def directories(
        self, predicate: Optional[DirectoryFilter] = None
    ) -> Generator[VersionedDirectory, None, None]:
        """a generator yielding all the directories found in the repository for
        the current commit, after applying the filter.

        Args:
            filter (Optional[DirectoryFilter]): an optional predicate to filter only specific directories.

        Yields:
            the next directory found (only for directories passing the filter).
        """
        return filter(
            lambda node: isinstance(node, VersionedDirectory), self.nodes(predicate)
        )

    def get_node(
        self, path: Path, filterable_gen: Optional[Callable] = None
    ) -> Optional[VersionedNode]:
        """Returns the node in the given path, None if it doesn't exist."""
        return next(self.nodes(lambda n: n.path == path), None)

    def get_directory(self, path: Path) -> Optional[VersionedDirectory]:
        """Returns the directory in the given path, None if it doesn't
        exist."""
        return next(self.directories(lambda n: n.path == path), None)

    def get_file(self, path: Path) -> Optional[VersionedFile]:
        """Returns the file in the given path, None if it doesn't exist."""
        return next(self.files(lambda n: n.path == path), None)

    @property
    def paths(self) -> List[Path]:
        """returns all the paths in the repo for the current commit (both files
        and directories)"""
        return [node.path for node in self.nodes()]

    def exists(self, path: Path) -> bool:
        """checks if a certain path exists in the repo in the current
        commit."""
        return path in self.paths

    def _nodes_in_tree(self, root: Tree) -> Generator[VersionedNode, None, None]:
        """a generator returning all the nodes (files and directories) under a
        certain git Tree (a versioned directory)."""
        # yield current directory
        yield VersionedDirectory(root, self._commit)
        # yield files under current directory
        for blob in root.blobs:
            yield VersionedFile(blob, self._commit)
        # yield subdirectories (and their children etc) under current directory
        for tree in root.trees:
            yield from self._nodes_in_tree(tree)
