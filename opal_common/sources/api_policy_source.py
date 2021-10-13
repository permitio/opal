import hashlib
from pathlib import Path
from tenacity import AsyncRetrying
from typing import Callable, Coroutine, List, Optional, Tuple
import aiohttp
from datetime import datetime
from fastapi import status
from git.objects import Commit
from tenacity.wait import wait_fixed
from opal_client.policy.fetcher import throw_if_bad_status_code
from opal_client.utils import tuple_to_dict

from opal_common.git.local_repo_utils import create_local_git, update_local_git
from opal_common.logger import logger
from opal_common.sources.base_policy_source import BasePolicySource
from opal_common.utils import get_authorization_header
from opal_server.config import opal_server_config

BundleHash = str


class ApiPolicySource(BasePolicySource):
    """
    Watches OPA like bundle server for changes and can trigger callbacks
    when detecting new bundle.

    Checking for changes is done by sending request to the remote bundle server.
    The pull can be either triggered by a method (i.e: you can
    call it from a webhook) or can be triggered periodically by a polling
    task.

    You can read more on OPA bundles here:
    https://www.openpolicyagent.org/docs/latest/management-bundles/

    Args:
        remote_source_url(str): the base address to request the policy from
        local_clone_path(str):  path for the local git to manage policies
        polling_interval(int):  how many seconds need to wait between polling
        token (str, optional):  auth token to include in connections to OPAL server. Defaults to POLICY_BUNDLE_SERVER_TOKEN.
    """

    def __init__(
        self,
        remote_source_url: str,
        local_clone_path: str,
        polling_interval: int = 0,
        token: Optional[str] = None,
    ):
        super().__init__(remote_source_url=remote_source_url, local_clone_path=local_clone_path,
                         polling_interval=polling_interval)
        self.token = token
        self.bundle_hash = None
        self.etag = None

    async def get_initial_policy_state_from_remote(self):
        """
        init remote data to local repo
        """
        async for attempt in AsyncRetrying(wait=wait_fixed(5)):
            with attempt:
                tmp_bundle_path, _, _ = await self.fetch_policy_bundle_from_api_source(self.remote_source_url, self.token)
                self.local_git = create_local_git(tmp_bundle_path=tmp_bundle_path, local_clone_path=self.local_clone_path)

    async def api_update_policy(self) -> Tuple[bool, str, str]:
        tmp_bundle_path, prev_version, current_hash = await self.fetch_policy_bundle_from_api_source(self.remote_source_url, self.token)
        if tmp_bundle_path and prev_version and current_hash:
            commit_msg = f"new version {current_hash}"
            self.local_git, prev_commit, new_commit = update_local_git(local_clone_path=self.local_clone_path, tmp_bundle_path=tmp_bundle_path, commit_msg=commit_msg)
            return True, prev_version, current_hash, prev_commit, new_commit
        else:
            return False, None, current_hash, None, None

    @staticmethod
    def hash_file(tmp_file_path):
        BUF_SIZE = 65536  # lets read stuff in 64kb chunks!
        sha256_hash = hashlib.sha256()
        with open(tmp_file_path, "rb") as file:
            while True:
                data = file.read(BUF_SIZE)
                if not data:
                    break
                sha256_hash.update(data)
        return sha256_hash.hexdigest()

    async def fetch_policy_bundle_from_api_source(
        self,
        url: str,
        token: Optional[str]
    ) -> Tuple[Path, BundleHash, BundleHash]:
        """
        Fetches the bundle. May throw, in which case we retry again.
        Checks that the bundle file isn't the same with Etag, if server
        doesn't have Etag it checks it with hash on the bundle file

        Read more on Etag here:
        https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/ETag

        Args:
            url(str): the base address to request the bundle.tar.gz file from
            token (str, optional): Auth token to include in connections to OPAL server. Defaults to POLICY_BUNDLE_SERVER_TOKEN.
        Returns:
            Path: bundle file path
            BundleHash: previous bundle hash on None
            BundleHash: current bundle hash

        """
        auth_headers = tuple_to_dict(
            get_authorization_header(token)) if token else {}
        etag_headers = {'ETag': self.etag,
                        "If-None-Match": self.etag} if self.etag else {}
        full_url = f"{url}/bundle.tar.gz"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{full_url}",
                    headers={'content-type': 'application/gzip',
                             **auth_headers, **etag_headers},
                ) as response:
                    if response.status == status.HTTP_404_NOT_FOUND:
                        logger.warning(
                            "requested url not found: {full_url}", full_url=full_url)
                        return None, None, None
                    if response.status == status.HTTP_304_NOT_MODIFIED:
                        logger.info(
                            "Not modified at: {now}", now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                        return False, None, None

                    # may throw ValueError
                    await throw_if_bad_status_code(response, expected=[status.HTTP_200_OK])
                    current_etag = response.headers.get("ETag", None)
                    response_bytes = await response.read()
                    tmp_file_path = Path(opal_server_config.POLICY_BUNDLE_TMP_PATH)
                    with open(tmp_file_path, "wb") as file:
                        file.write(response_bytes)

                    if not current_etag:
                        logger.info('Etag is turnned off, you may want to turn it on at your bundle server')
                        current_bundle_hash = ApiPolicySource.hash_file(tmp_file_path)
                        logger.info('Bundle hash is {hash}', hash=current_bundle_hash)
                        if self.bundle_hash == current_bundle_hash:
                            logger.info("No new bundle, hash is: {hash}", hash=current_bundle_hash)
                            return False, None, current_bundle_hash
                        else:
                            logger.info("New bundle found, hash is: {hash}", hash=current_bundle_hash)
                            prev_bundle_hash = self.bundle_hash
                            self.bundle_hash = current_bundle_hash
                            return tmp_file_path, prev_bundle_hash, current_bundle_hash
                    else:
                        prev_etag = self.etag
                        self.etag = current_etag
                        return tmp_file_path, prev_etag, current_etag

            except aiohttp.ClientError as e:
                logger.warning("server connection error: {err}", err=repr(e))
                raise

    async def check_for_changes(self):
        """
        Calling this method will trigger an api check to the remote.
        If after the request the watcher detects new bundle, it will call the
        callbacks registered with _on_new_policy().
        """
        logger.info(
            "Fetching changes from remote: '{remote}'", remote=self.remote_source_url)
        has_changes, prev, latest, prev_commit, new_commit = await self.api_update_policy()
        if not has_changes:
            logger.info(
                "No new version: current hash is: '{head}'", head=latest)
        else:
            logger.info(
                "Found new version: old version hash was '{prev_head}', new version hash is '{new_head}'",
                prev_head=prev, new_head=latest)
            await self._on_new_policy(old=prev_commit, new=new_commit)
