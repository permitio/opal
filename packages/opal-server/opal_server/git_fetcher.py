from pathlib import Path
from typing import cast

import aiofiles.os
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.policy_source import SSHAuthData
from opal_common.schemas.scopes import Scope
from pygit2 import (
    KeypairFromMemory,
    RemoteCallbacks,
    Username,
    clone_repository,
    discover_repository,
)


class GitPolicyFetcher:
    def __init__(self, base_dir: Path, scope: Scope):
        self._base_dir = _get_scope_dir(base_dir)
        self._scope = scope
        self._auth_callbacks = _GitCallback(self._scope)
        self._repo_path = self._base_dir / scope.scope_id

    async def fetch(self):
        await aiofiles.os.makedirs(str(self._base_dir), exist_ok=True)

        if discover_repository(str(self._repo_path)):
            await self._pull()
        else:
            await self._clone()

    async def _clone(self):
        clone_repository(
            self._scope.policy.url,
            str(self._repo_path),
            callbacks=self._auth_callbacks,
            checkout_branch=self._scope.policy.branch,
        )

    async def _pull(self):
        pass

    async def make_bundle(self) -> PolicyBundle:
        pass


class _GitCallback(RemoteCallbacks):
    def __init__(self, scope: Scope):
        super().__init__()
        self._scope = scope

    def credentials(self, url, username_from_url, allowed_types):
        if isinstance(self._scope.policy.auth, SSHAuthData):
            auth = cast(SSHAuthData, self._scope.policy.auth)

            return KeypairFromMemory(
                username=username_from_url,
                pubkey=auth.public_key or "",
                privkey=auth.private_key,
                passphrase="",
            )

        return Username(username_from_url)


def _get_scope_dir(base_dir: Path):
    return base_dir / "scopes"
