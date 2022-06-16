from opal_common.schemas.policy_source import (
    GitPolicyScopeSource,
    NoAuthData,
    SSHAuthData,
)
from opal_common.schemas.scopes import Scope
from opal_server.config import ServerRole, opal_server_config
from opal_server.scopes.scope_repository import ScopeRepository

DEFAULT_SCOPE_ID = "default"


async def load_scopes(repo: ScopeRepository):
    if opal_server_config.SERVER_ROLE == ServerRole.Leader:
        await _load_env_scope(repo)


async def _load_env_scope(repo: ScopeRepository):
    # backwards compatible opal scope
    if opal_server_config.POLICY_REPO_URL is not None:
        auth = NoAuthData()

        if opal_server_config.POLICY_REPO_SSH_KEY is not None:
            auth = SSHAuthData(
                username="git", private_key=opal_server_config.POLICY_REPO_SSH_KEY
            )

        scope = Scope(
            scope_id=DEFAULT_SCOPE_ID,
            policy=GitPolicyScopeSource(
                source_type=opal_server_config.POLICY_SOURCE_TYPE.lower(),
                url=opal_server_config.POLICY_REPO_URL,
                manifest=opal_server_config.POLICY_REPO_MANIFEST_PATH,
                branch=opal_server_config.POLICY_REPO_MAIN_BRANCH,
                auth=auth,
            ),
        )

        await repo.put(scope)
