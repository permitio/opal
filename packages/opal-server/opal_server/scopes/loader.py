import asyncio
import random

from opal_common.http_utils import redact_url
from opal_common.logger import logger
from opal_common.schemas.policy_source import (
    GitPolicyScopeSource,
    NoAuthData,
    SSHAuthData,
)
from opal_common.schemas.scopes import Scope
from opal_server import broadcast_redis
from opal_server.config import ServerRole, opal_server_config
from opal_server.scopes.scope_repository import ScopeRepository
from redis.exceptions import RedisError

DEFAULT_SCOPE_ID = "default"

# Storing the default scope is bounded and retried as the Redis broadcaster
# bounds a publish and backs off its resubscribes.
_STORE_TIMEOUT_SECONDS = broadcast_redis.PUBLISH_TIMEOUT_SECONDS
_RETRY_MIN_SECONDS = broadcast_redis.RESUBSCRIBE_BACKOFF_MIN_SECONDS
_RETRY_MAX_SECONDS = broadcast_redis.RESUBSCRIBE_BACKOFF_MAX_SECONDS


async def load_scopes(repo: ScopeRepository):
    """Store the default scope (POLICY_REPO_URL) when there is one.

    The leader runs it once it holds the leadership lock. Each try has
    10 seconds; one that Redis refuses or does not answer in time is logged
    at ERROR and tried again, from 0.5 seconds doubling to 30, until Redis
    answers. Cancelling it stops the tries.

    Raises:
        Whatever is not a Redis failure or a timeout, at once.
    """
    logger.info("Server is primary, loading default scope.")
    await _load_env_scope(repo)


async def _store(repo: ScopeRepository, scope: Scope) -> None:
    attempt = 0
    while True:
        attempt += 1
        try:
            async with asyncio.timeout(_STORE_TIMEOUT_SECONDS):
                await repo.put(scope)
        except (RedisError, OSError, TimeoutError) as e:
            exponent = min(attempt - 1, 32)
            base = min(_RETRY_MIN_SECONDS * 2**exponent, _RETRY_MAX_SECONDS)
            # Equal jitter, as the broadcaster's: pods do not retry in step.
            delay = base / 2 + random.uniform(0, base / 2)
            logger.error(
                "Could not store the default scope in Redis (try {attempt}, "
                "{timeout:g}s each): {err}; trying again in {delay:.1f}s. Until "
                "it is stored the scopes leader syncs nothing",
                attempt=attempt,
                timeout=_STORE_TIMEOUT_SECONDS,
                err=f"{type(e).__name__}: {e}",
                delay=delay,
            )
            await asyncio.sleep(delay)
            continue
        if attempt > 1:
            logger.info(
                "Stored the default scope in Redis after {attempt} tries",
                attempt=attempt,
            )
        return


async def _load_env_scope(repo: ScopeRepository):
    # backwards compatible opal scope
    if opal_server_config.POLICY_REPO_URL is not None:
        logger.info(
            "Adding default scope from env: {url}",
            url=redact_url(opal_server_config.POLICY_REPO_URL),
        )

        auth = NoAuthData()

        if opal_server_config.POLICY_REPO_SSH_KEY is not None:
            private_ssh_key = opal_server_config.POLICY_REPO_SSH_KEY
            private_ssh_key = private_ssh_key.replace("_", "\n")

            if not private_ssh_key.endswith("\n"):
                private_ssh_key += "\n"

            auth = SSHAuthData(username="git", private_key=private_ssh_key)

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

        await _store(repo, scope)
