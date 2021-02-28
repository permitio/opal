from typing import IO, Generator, Callable, Optional, List, Set

from git import Repo
from git.objects import Commit, Tree, Blob, IndexObject
from pathlib import Path

from opal.common.paths import PathUtils

class VersionedNode:
    def __init__(self, node: IndexObject, commit: Commit):
        self._node = node
        self._commit = commit
        self._repo: Repo = commit.repo

    @property
    def repo(self) -> Repo:
        return self._repo

    @property
    def commit(self) -> Commit:
        return self._commit

    @property
    def version(self) -> str:
        return self._commit.hexsha

    @property
    def path(self) -> Path:
        return Path(self._node.path)

class VersionedFile(VersionedNode):
    def __init__(self, blob: Blob, commit: Commit):
        super().__init__(blob, commit)
        self._blob: Blob = blob

    @property
    def blob(self) -> Blob:
        return self._blob

    @property
    def stream(self) -> IO:
        return self.blob.data_stream

    def read_bytes(self) -> bytes:
        return self.stream.read()

    def read(self, encoding='utf-8') -> str:
        return self.read_bytes().decode(encoding=encoding)

class VersionedDirectory(VersionedNode):
    def __init__(self, directory: Tree, commit: Commit):
        super().__init__(directory, commit)
        self._dir: Tree = directory

    @property
    def dir(self) -> Tree:
        return self._dir


NodeFilter = Callable[[VersionedNode], bool]
FileFilter = Callable[[VersionedFile], bool]
DirectoryFilter = Callable[[VersionedDirectory], bool]


def has_extension(f: VersionedFile, extensions: Optional[List[str]] = None) -> bool:
    if extensions is None:
        return True # no filter
    else:
        return f.path.suffix in extensions


def is_under_directories(f: VersionedFile, directories: Set[Path]) -> bool:
    return PathUtils.is_child_of_directories(f.path, directories)


class CommitViewer:
    """
    This class allows us to view the repository files from the perspecitive
    of a specific commit.

    i.e: if in the last commit (HEAD-1) we removed a file a.txt, we will see it
    while initializing CommitViewer with commit=HEAD-1, but we will not see a.txt
    if we initialize the CommitViewer with the HEAD commit.

    The viewer also allows us to filter out paths of the commit tree.
    """
    def __init__(self, commit: Commit):
        self._repo: Repo = commit.repo
        self._commit = commit
        self._root = commit.tree

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def nodes(self, filter: Optional[NodeFilter] = None) -> Generator[VersionedNode, None, None]:
        nodes_generator = self._nodes_in_tree(self._root)
        if filter is None:
            yield from nodes_generator
        else:
            for node in nodes_generator:
                if filter(node):
                    yield node

    def files(self, filter: Optional[FileFilter] = None) -> Generator[VersionedFile, None, None]:
        files_generator = self.nodes(lambda node: isinstance(node, VersionedFile))
        if filter is None:
            yield from files_generator
        else:
            for f in files_generator:
                if filter(f):
                    yield f

    def directories(self, filter: Optional[DirectoryFilter] = None) -> Generator[VersionedDirectory, None, None]:
        dir_generator = self.nodes(lambda node: isinstance(node, VersionedDirectory))
        if filter is None:
            yield from dir_generator
        else:
            for directory in dir_generator:
                if filter(directory):
                    yield directory

    @property
    def paths(self) -> List[Path]:
        return [node.path for node in self.nodes()]

    def exists(self, path: Path) -> bool:
        return path in self.paths

    def _nodes_in_tree(self, root: Tree) -> Generator[VersionedNode, None, None]:
        # yield current directory
        yield VersionedDirectory(root, self._commit)
        # yield files under current directory
        for blob in root.blobs:
            yield VersionedFile(blob, self._commit)
        # yield subdirectories (and their children etc) under current directory
        for tree in root.trees:
            yield from self._nodes_in_tree(tree)

