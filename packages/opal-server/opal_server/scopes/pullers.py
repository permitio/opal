import dataclasses
from abc import ABC, abstractmethod
from pathlib import Path
from typing import cast

import pygit2
from pygit2 import discover_repository, clone_repository, Repository, RemoteCallbacks, KeypairFromMemory, Username, \
    UserPass

from opal_common.scopes.scopes import Scope
from opal_common.scopes.sources import SourceAuthData, SSHAuthData, GitHubTokenAuthData, GitPolicySource


class SourcePuller(ABC):
    def check(self) -> bool:
        return False

    @abstractmethod
    def pull(self):
        pass

    def diff(self) -> (str, str):
        return None, None


@dataclasses.dataclass
class InvalidScopeSourceType(Exception):
    invalid_type: str


@dataclasses.dataclass
class GitError(Exception):
    error: str


class GitSourcePuller(SourcePuller):
    def __init__(self, scope_id: str, base_dir: Path, source: GitPolicySource):
        self.scope_id = scope_id
        self.base_dir = base_dir
        self.source = source

    def check(self) -> bool:
        """
        returns True if new commits are available, false if up-to-date
        """
        if discover_repository(str(self._get_repo_path())) is None:
            return True

        repo = Repository(self._get_repo_path())
        callbacks = self._get_callbacks()

        repo.remotes['origin'].fetch(callbacks=callbacks)
        latest_hash = repo.references['refs/remotes/origin/master'].target

        return latest_hash != repo.head.target

    def pull(self):
        try:
            self._pull()
        except pygit2.GitError as e:
            raise GitError(str(e))

    def diff(self) -> (str, str):
        repo = Repository(self._get_repo_path())
        return repo.head.target, repo.references['refs/remotes/origin/master'].target

    def _pull(self):
        repo_path = self._get_repo_path()
        callbacks = self._get_callbacks()

        if discover_repository(str(repo_path)) is None:
            clone_repository(self.source.url, str(self.base_dir/self.scope_id), callbacks=callbacks)
        else:
            repo = Repository(repo_path)
            repo.remotes['origin'].fetch(callbacks=callbacks)
            repo.checkout(repo.references['refs/remotes/origin/master'].resolve().name)

    def _get_repo_path(self):
        return self.base_dir / self.scope_id

    def _get_callbacks(self):
        return GitCallbacks(self.source.auth)


class GitCallbacks(RemoteCallbacks):
    def __init__(self, auth_data: SourceAuthData):
        super().__init__()
        self._auth_data = auth_data

    def credentials(self, url, username_from_url, allowed_types):
        if self._auth_data.auth_type == 'ssh':
            ssh_auth_data = cast(SSHAuthData, self._auth_data)

            return KeypairFromMemory(
                username=username_from_url,
                pubkey=ssh_auth_data.public_key,
                privkey=ssh_auth_data.private_key,
                passphrase=""
            )
        elif self._auth_data.auth_type == 'github_token':
            github_token_data = cast(GitHubTokenAuthData, self._auth_data)

            return UserPass(
                username="x-access-token",
                password=github_token_data.token
            )

        return Username(username_from_url)


def create_puller(base_dir: Path, scope: Scope):
    if scope.policy.source_type == 'git':
        auth_props = scope.policy.settings.get('auth', {})
        auth = SourceAuthData(**auth_props)

        if auth.auth_type == 'github_token':
            auth = GitHubTokenAuthData(**auth_props)

        policy_source = GitPolicySource(
            source_type=scope.policy.source_type,
            url=scope.policy.url,
            directories=scope.policy.directories,
            auth=auth
        )

        return GitSourcePuller(scope.scope_id, base_dir, policy_source)
    else:
        raise InvalidScopeSourceType(scope.policy.source_type)
