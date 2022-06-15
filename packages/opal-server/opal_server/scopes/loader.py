from opal_common.schemas.policy_source import PolicySource
from opal_common.schemas.scopes import Scope
from opal_server.config import opal_server_config
from opal_server.scopes.scope_repository import ScopeRepository


async def load_scopes(repo: ScopeRepository):
    await _load_env_scope(repo)


async def _load_env_scope(repo: ScopeRepository):
    # backwards compatible opal scope
    if opal_server_config.POLICY_REPO_URL is not None:
        scope = Scope(
            scope_id="env",
            policy=PolicySource(
                source_type=opal_server_config.POLICY_SOURCE_TYPE.lower(),
                url=opal_server_config.POLICY_REPO_URL,
                manifest=opal_server_config.POLICY_REPO_MANIFEST_PATH,
            )
        )

        await repo.put(scope)

