from pathlib import Path
from typing import cast

import aiofiles.os
from opal_common.logger import logger
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import GitPolicySource, SSHAuthData
from pygit2 import (
    KeypairFromMemory,
    RemoteCallbacks,
    Repository,
    Username,
    clone_repository,
    discover_repository,
)


class GitPolicyFetcher:
    def __init__(self, base_dir: Path, scope_id: str, source: GitPolicySource):
        self._base_dir = _get_scope_dir(base_dir)
        self._source = source
        self._auth_callbacks = _GitCallback(self._source)
        self._repo_path = self._base_dir / scope_id

    async def fetch(self):
        await aiofiles.os.makedirs(str(self._base_dir), exist_ok=True)

        if discover_repository(str(self._repo_path)):
            await self._pull()
        else:
            await self._clone()

    async def _clone(self):
        logger.info("Cloning new scope to {path}", path=self._repo_path)
        clone_repository(
            self._source.url,
            str(self._repo_path),
            callbacks=self._auth_callbacks,
            checkout_branch=self._source.branch,
        )

    async def _pull(self):
        logger.info("Checking for new commits in {path}", path=self._repo_path)
        repo = Repository(self._repo_path)
        repo.remotes["origin"].fetch(callbacks=self._auth_callbacks)
        repo.checkout(
            repo.references[f"refs/remotes/origin/{self._source.branch}"].resolve().name
        )

    async def make_bundle(self) -> PolicyBundle:
        pass


class _GitCallback(RemoteCallbacks):
    def __init__(self, source: GitPolicySource):
        super().__init__()
        self._source = source

    def credentials(self, url, username_from_url, allowed_types):
        if isinstance(self._source.auth, SSHAuthData):
            auth = cast(SSHAuthData, self._source.auth)

            return KeypairFromMemory(
                username=username_from_url,
                pubkey=auth.public_key or "",
                privkey=auth.private_key,
                passphrase="",
            )

        return Username(username_from_url)


def _get_scope_dir(base_dir: Path):
    return base_dir / "scopes"
