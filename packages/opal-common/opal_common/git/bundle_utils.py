from pathlib import Path
from typing import List

from opal_common.schemas.policy import DataModule, PolicyBundle, RegoModule


class BundleUtils:
    MAX_INDEX = 10000

    @staticmethod
    def sorted_policy_modules_to_load(bundle: PolicyBundle) -> List[RegoModule]:
        """policy modules sorted according to manifest."""
        manifest_paths = [Path(path) for path in bundle.manifest]

        def key_function(module: RegoModule) -> int:
            """this method reduces the module to a number that can be act as
            sorting key.

            the number is the index in the manifest list, so basically
            we sort according to manifest.
            """
            try:
                return manifest_paths.index(Path(module.path))
            except ValueError:
                return BundleUtils.MAX_INDEX

        return sorted(bundle.policy_modules, key=key_function)

    @staticmethod
    def sorted_data_modules_to_load(bundle: PolicyBundle) -> List[DataModule]:
        """data modules sorted according to manifest."""
        manifest_paths = [Path(path) for path in bundle.manifest]

        def key_function(module: DataModule) -> int:
            try:
                return manifest_paths.index(Path(module.path))
            except ValueError:
                return BundleUtils.MAX_INDEX

        return sorted(bundle.data_modules, key=key_function)

    @staticmethod
    def sorted_policy_modules_to_delete(bundle: PolicyBundle) -> List[Path]:
        # already sorted
        return bundle.deleted_files.policy_modules

    @staticmethod
    def sorted_data_modules_to_delete(bundle: PolicyBundle) -> List[Path]:
        # already sorted
        return bundle.deleted_files.data_modules
