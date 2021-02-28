from functools import partial
from pathlib import Path
from typing import List, Optional, Set

from git import Repo
from git.objects import Commit

from opal.common.git.commit_viewer import CommitViewer, has_extension, is_under_directories
from opal.common.git.diff_viewer import DiffViewer, diffed_file_has_extension, diffed_file_is_under_directories
from opal.common.opa import get_rego_package, is_data_module, is_rego_module
from opal.common.schemas.policy import DataModule, PolicyBundle, RegoModule, DeletedFiles


class BundleMaker:
    """
    creates a policy bundle based on input parameters.
    """
    def __init__(self, repo: Repo, in_directories: Set[Path], extensions: Optional[List[str]] = None):
        self._repo = repo
        self._directories = in_directories
        self._has_extension = partial(has_extension, extensions=extensions)
        self._is_under_directories = partial(is_under_directories, directories=in_directories)
        self._diffed_file_has_extension = partial(diffed_file_has_extension, extensions=extensions)
        self._diffed_file_is_under_directories = partial(diffed_file_is_under_directories, directories=in_directories)

    def make_bundle(self, commit: Commit) -> PolicyBundle:
        data_modules = []
        rego_modules = []
        manifest = []

        with CommitViewer(commit) as viewer:
            filter = lambda f: self._has_extension(f) and self._is_under_directories(f)
            for source_file in viewer.files(filter):
                contents = source_file.read()
                path = source_file.path

                if is_data_module(path):
                    data_modules.append(
                        DataModule(path=str(path.parent), data=contents)
                    )
                elif is_rego_module(path):
                    rego_modules.append(
                        RegoModule(
                            path=str(path),
                            package_name=get_rego_package(contents) or "",
                            rego=contents,
                        )
                    )
                else:
                    continue

                manifest.append(str(path)) # only returns the relative path

            return PolicyBundle(
                manifest=manifest,
                hash=commit.hexsha,
                data_modules=data_modules,
                rego_modules=rego_modules,
            )

    def make_diff_bundle(self, old_commit: Commit, new_commit: Commit) -> PolicyBundle:
        data_modules = []
        rego_modules = []
        deleted_data_modules = []
        deleted_rego_modules = []
        manifest = []

        with DiffViewer(old_commit, new_commit) as viewer:
            filter = lambda diff: (
                self._diffed_file_has_extension(diff) and \
                    self._diffed_file_is_under_directories(diff)
                )
            for source_file in viewer.added_or_modified_files(filter):
                contents = source_file.read()
                path = source_file.path

                if is_data_module(path):
                    data_modules.append(
                        DataModule(path=str(path.parent), data=contents)
                    )
                elif is_rego_module(path):
                    rego_modules.append(
                        RegoModule(
                            path=str(path),
                            package_name=get_rego_package(contents) or "",
                            rego=contents,
                        )
                    )
                else:
                    continue

                manifest.append(str(path)) # only returns the relative path

            for source_file in viewer.deleted_files(filter):
                path = source_file.path

                if is_data_module(path):
                    deleted_data_modules.append(path)
                elif is_rego_module(path):
                    deleted_rego_modules.append(path)

            if deleted_data_modules or deleted_rego_modules:
                deleted_files = DeletedFiles(
                    data_modules=deleted_data_modules,
                    rego_modules=deleted_rego_modules,
                )
            else:
                deleted_files = None

            return PolicyBundle(
                manifest=manifest,
                hash=new_commit.hexsha,
                old_hash=old_commit.hexsha,
                data_modules=data_modules,
                rego_modules=rego_modules,
                deleted_files=deleted_files
            )