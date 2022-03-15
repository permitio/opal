from functools import partial
from pathlib import Path
from typing import List, Optional, Set

from git import Repo
from git.objects import Commit

from opal_common.paths import PathUtils
from opal_common.git.commit_viewer import CommitViewer, VersionedFile, has_extension, is_under_directories
from opal_common.git.diff_viewer import DiffViewer, diffed_file_has_extension, diffed_file_is_under_directories
from opal_common.opa import get_rego_package, is_data_module, is_rego_module
from opal_common.schemas.policy import DataModule, PolicyBundle, RegoModule, DeletedFiles


class BundleMaker:
    """
    creates a policy bundle based on:
    - the current state of the policy git repo
    - filtering criteria on the policy git repo (specific directories, specific file types, etc)

    there are two types of bundles:
    - a full/complete bundle, representing the state of the repo at one commit
    - a diff bundle, representing only the *changes* made to the policy between two commits (the diff).
    """
    def __init__(self, repo: Repo, in_directories: Set[Path], extensions: Optional[List[str]] = None, manifest_filename: str = ".manifest"):
        """[summary]

        Args:
            repo (Repo): the policy repo
            in_directories (Set[Path]): the directories in the repo that we want to filter on.
                if the entire repo is relevant, pass Path(".") as the directory
                (all paths are relative to the repo root).
            extensions (Optional[List[str]]): optional filtering on file extensions.
        """
        self._repo = repo
        self._directories = in_directories
        self._has_extension = partial(has_extension, extensions=extensions)
        self._is_under_directories = partial(is_under_directories, directories=in_directories)
        self._diffed_file_has_extension = partial(diffed_file_has_extension, extensions=extensions)
        self._diffed_file_is_under_directories = partial(diffed_file_is_under_directories, directories=in_directories)
        self._manifest_filename = manifest_filename

    def _get_explicit_manifest(self, viewer: CommitViewer) -> Optional[List[str]]:
        """
        Rego policies often have dependencies (import statements) between policies.
        Since the OPAL client is limited by the OPA REST api and this api currently does not allow
        to load bundles (multiple policies together), OPAL client can only load one policy at a time.

        If policies with dependencies between them are loaded out-of-order, OPA will throw an exception.

        To mitigate this, we allow the developer to put a manifest file in the repository (default path: .manifest).
        This file, if exists, should contain the list of policy files (.rego) in the correct order they should be
        loaded into OPA.

        This method searches for an explicit manifest file, reads it and returns the list of paths, or None if not found.
        """
        def is_manifest_file(f: VersionedFile) -> bool:
            return f.path == Path(self._manifest_filename)

        manifest_files = list(viewer.files(is_manifest_file))
        if not manifest_files:
            return None

        try:
            manifest_paths = [Path(path) for path in manifest_files[0].read().splitlines()]
            return [str(path) for path in manifest_paths if viewer.exists(path)]
        except:
            return None

    def _sort_manifest(self, unsorted_manifest: List[str], explicit_sorting: Optional[List[str]]) -> List[str]:
        """
        the way this sorting works, is assuming that explicit_sorting does NOT necessarily contains all the policies
        found in the manifest, or that even "policies" mentioned in it actually exists in the actual generated manifest.
        We must ensure that all items in unsorted_manifest must also exist in the output list.
        """
        if not explicit_sorting:
            return unsorted_manifest

        # casting to Path
        unsorted_paths = [Path(path) for path in unsorted_manifest]
        sorting = [Path(path) for path in explicit_sorting]

        # sorting the list
        sorted_paths = PathUtils.sort_paths_according_to_explicit_sorting(unsorted_paths, sorting)

        # cast back to string paths
        return [str(path) for path in sorted_paths]

    def make_bundle(self, commit: Commit) -> PolicyBundle:
        """
        creates a *complete* bundle of all the policy and data modules found
        in the policy repo, when the repo HEAD is at the given `commit`.

        Args:
            commit (Commit): the commit the repo should be checked out on to search for policy files.

        Returns:
            bundle (PolicyBundle): the bundle of policy modules found in the repo (checked out on `commit`)
        """
        data_modules = []
        policy_modules = []
        manifest = []

        with CommitViewer(commit) as viewer:
            filter = lambda f: self._has_extension(f) and self._is_under_directories(f)
            explicit_manifest = self._get_explicit_manifest(viewer)
            for source_file in viewer.files(filter):
                contents = source_file.read()
                path = source_file.path

                if is_data_module(path):
                    data_modules.append(
                        DataModule(path=str(path.parent), data=contents)
                    )
                elif is_rego_module(path):
                    policy_modules.append(
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
                manifest=self._sort_manifest(manifest, explicit_manifest),
                hash=commit.hexsha,
                data_modules=data_modules,
                policy_modules=policy_modules,
            )

    def make_diff_bundle(self, old_commit: Commit, new_commit: Commit) -> PolicyBundle:
        """
        creates a *diff* bundle of all the policy and data modules that were changed
        (either added, renamed, modified or deleted) between the `old_commit` and `new_commit`.
        essentially all the relevant files when running `git diff old_commit..new_commit`.

        Note that we still filter only directories and file types given in the constructor.

        Args:
            old_commit (Commit): represents the previous known state of the repo.
                The opal client subscribes to the policy state and gets updates from
                the server via a pubsub channel. When it receives an update that
                new state is available in the policy repo, the client requests a
                *diff bundle* from the /policy api route. The client will report
                its last known commit as the `old_commit`, and only new state
                (the diff from the client known commit to the server newest commit)
                will be returned back.
            commit (Commit): represents the newest known commit in the server (the new state).

        Returns:
            bundle (PolicyBundle): a diff bundle containing only the policy modules changed
                between `old_commit` and `new_commit`.
        """
        data_modules = []
        policy_modules = []
        deleted_data_modules = []
        deleted_policy_modules = []
        manifest = []
        explicit_manifest = self._get_explicit_manifest(CommitViewer(new_commit))

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
                        # in OPA, the data module path is the containing directory
                        # i.e: /path/to/data.json will put the json contents under "/path/to" in the opa tree
                        DataModule(path=str(path.parent), data=contents)
                    )
                elif is_rego_module(path):
                    policy_modules.append(
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
                    # in OPA, the data module path is the containing directory (see above)
                    deleted_data_modules.append(str(path.parent))
                elif is_rego_module(path):
                    deleted_policy_modules.append(path)

            if deleted_data_modules or deleted_policy_modules:
                deleted_policies = self._sort_manifest(deleted_policy_modules, explicit_manifest)
                deleted_policies.reverse() # when removed, dependent policies should be removed first

                deleted_files = DeletedFiles(
                    data_modules=deleted_data_modules,
                    policy_modules=deleted_policies,
                )
            else:
                deleted_files = None

            return PolicyBundle(
                manifest=self._sort_manifest(manifest, explicit_manifest),
                hash=new_commit.hexsha,
                old_hash=old_commit.hexsha,
                data_modules=data_modules,
                policy_modules=policy_modules,
                deleted_files=deleted_files
            )
