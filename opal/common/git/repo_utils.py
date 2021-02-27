from typing import Optional, List, Generator

from pathlib import Path
from git import Repo, DiffIndex
from git.objects.commit import Commit
from git.objects.tree import Tree

from opal.common.utils import sorted_list_from_set
from opal.common.schemas.policy import PolicyBundle, DataModule, RegoModule
from opal.common.opa import get_rego_package, is_rego_module, is_data_module


class GitFailed(Exception):
    """
    an exception we throw on git failures that are caused by wrong assumptions.
    i.e: we want to track a non-existing branch, or git url is not valid.
    """
    def __init__(self, exc: Exception):
        self._original_exc = exc
        super().__init__()


class GitActions:
    @classmethod
    def repo_dir(cls, repo: Repo) -> Path:
        return Path(repo.git_dir).parent

    @classmethod
    def files_in_tree(cls, root: Tree, path: Path = Path(".")) -> Generator[Path, None, None]:
        for blob in root.blobs:
            yield path / blob.name
        for tree in root.trees:
            yield from cls.files_in_tree(tree, path / tree.name)

    @classmethod
    def all_files_in_repo(cls,
        commit: Commit,
        extensions: Optional[List[str]] = None,
        relative_to: Path = Path(".")
    ) -> List[Path]:
        """
        get all files in repo, for a specific commit.
        """
        all_paths = list(cls.files_in_tree(commit.tree, path=relative_to))
        if extensions is None:
            return all_paths
        return [path for path in all_paths if path.suffix in extensions]

    @classmethod
    def diff_between_commits(cls, old: Commit, new: Commit) -> DiffIndex:
        return old.diff(new)

    @classmethod
    def files_affected_in_diff(cls, diff_list: DiffIndex) -> List[Path]:
        return []

    @classmethod
    def create_bundle(
        cls,
        repo: Repo,
        commit: Commit,
        parent_dirs: List[Path],
        extensions: Optional[List[str]] = None
    ) -> PolicyBundle:
        repo_dir = GitActions.repo_dir(repo)

        opa_files_in_repo = GitActions.all_files_in_repo(
            commit, extensions=extensions, relative_to=repo_dir
        )
        paths = DirActions.filter_paths_under_parents(opa_files_in_repo, parent_dirs)

        data_modules = []
        rego_modules = []
        manifest = []
        for path in paths:
            with path.open() as f:
                contents = f.read()
                rel_path = path.relative_to(repo_dir)

                if is_data_module(rel_path):
                    data_modules.append(DataModule(path=str(rel_path.parent), data=contents))
                elif is_rego_module(rel_path):
                    rego_modules.append(RegoModule(
                        path=str(rel_path),
                        package_name=get_rego_package(contents) or "",
                        rego=contents,
                    ))
                else:
                    continue
            manifest.append(str(rel_path)) # only returns the relative path

        return PolicyBundle(
            manifest=manifest,
            hash=commit.hexsha,
            data_modules=data_modules,
            rego_modules=rego_modules,
        )

class DirActions:
    @classmethod
    def parents(cls, paths: List[Path]) -> List[Path]:
        """
        returns the set of all parent directories of a list of paths
        """
        all_parents = set()
        for path in paths:
            all_parents.update(path.parents)
        return sorted_list_from_set(all_parents)

    @classmethod
    def filter_paths_under_parents(cls, input_paths: List[Path], parents: List[Path]) -> List[Path]:
        """
        returns only paths in :input_paths that are children of one of the paths in :parents.
        """
        parent_set = set(parents)
        paths = []
        for path in input_paths:
            if parent_set & set(path.parents):
                paths.append(path)
        return paths