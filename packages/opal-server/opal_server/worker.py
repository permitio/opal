import shutil
from functools import partial
from pathlib import Path
from typing import List, Optional, Set, cast

import git
from aiohttp import ClientError, ClientSession
from asgiref.sync import async_to_sync
from celery import Celery
from fastapi import status
from opal_common.git.commit_viewer import VersionedFile
from opal_common.logger import configure_logs, logger
from opal_common.schemas.policy import PolicyUpdateMessageNotification
from opal_common.schemas.policy_source import GitPolicyScopeSource
from opal_common.schemas.scopes import Scope
from opal_common.utils import get_authorization_header, tuple_to_dict
from opal_server.config import opal_server_config
from opal_server.git_fetcher import GitPolicyFetcher, PolicyFetcherCallbacks
from opal_server.policy.watcher.callbacks import (
    create_policy_update,
    create_update_all_directories_in_repo,
)
from opal_server.redis import RedisDB
from opal_server.scopes.scope_repository import ScopeRepository


def is_rego_source_file(
    f: VersionedFile, extensions: Optional[List[str]] = None
) -> bool:
    """filters only rego files or data.json files."""
    REGO = ".rego"
    JSON = ".json"
    OPA_JSON = "data.json"

    if extensions is None:
        extensions = [REGO, JSON]
    if JSON in extensions and f.path.suffix == JSON:
        return f.path.name == OPA_JSON
    return f.path.suffix in extensions


class NewCommitsCallbacks(PolicyFetcherCallbacks):
    def __init__(
        self,
        base_dir: Path,
        scope_id: str,
        source: GitPolicyScopeSource,
        http: ClientSession,
    ):
        self._scope_repo_dir = GitPolicyFetcher.repo_clone_path(base_dir, source)
        self._scope_id = scope_id
        self._source = source
        self._http = http

    async def on_update(self, previous_head: str, head: str):
        if previous_head == head:
            logger.info(
                f"scope '{self._scope_id}': No new commits, HEAD is at '{head}'"
            )
            return

        logger.info(
            f"scope '{self._scope_id}': Found new commits: old HEAD was '{previous_head}', new HEAD is '{head}'"
        )
        if not self._scope_repo_dir.exists():
            logger.error(
                f"on_update({self._scope_id}) was triggered, but repo path is not found: {self._scope_repo_dir}"
            )
            return

        try:
            repo = git.Repo(self._scope_repo_dir)
        except git.GitError as exc:
            logger.error(
                f"Got exception for repo in path: {self._scope_repo_dir}, scope_id: {self._scope_id}, error: {exc}"
            )
            return

        notification: Optional[PolicyUpdateMessageNotification] = None
        predicate = partial(is_rego_source_file, extensions=self._source.extensions)
        if previous_head is None:
            notification = await create_update_all_directories_in_repo(
                repo.commit(head), repo.commit(head), predicate=predicate
            )
        else:
            notification = await create_policy_update(
                repo.commit(previous_head),
                repo.commit(head),
                self._source.extensions,
                predicate=predicate,
            )

        if notification is not None:
            await self.trigger_notification(notification)

    async def trigger_notification(self, notification: PolicyUpdateMessageNotification):
        logger.info(
            f"Triggering policy update for scope {self._scope_id}: {notification.dict()}"
        )

        url = f"{opal_server_config.SERVER_URL}/scopes/{self._scope_id}/policy/update"
        try:
            async with self._http.post(
                url,
                json=notification.dict(),
                headers=tuple_to_dict(
                    get_authorization_header(opal_server_config.WORKER_TOKEN)
                ),
            ) as response:
                if response.status == status.HTTP_204_NO_CONTENT:
                    logger.debug(
                        f"triggered policy notification for {self._scope_id} via the api"
                    )
                else:
                    logger.error(
                        f"could not trigger policy notification for {self._scope_id} via the api, got status={response.status}"
                    )
        except ClientError as e:
            logger.error("opal server connection error: {err}", err=repr(e))


class Worker:
    def __init__(self, base_dir: Path, scopes: ScopeRepository):
        self._base_dir = base_dir
        self._scopes = scopes
        self._http: Optional[ClientSession] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self):
        self._http = ClientSession()

    async def stop(self):
        await self._http.close()

    async def sync_scope(
        self,
        scope_id: str,
        hinted_hash: Optional[str] = None,
        force_fetch: bool = False,
    ):
        logger.info(f"Sync scope: {scope_id}")
        scope = await self._scopes.get(scope_id)

        if not isinstance(scope.policy, GitPolicyScopeSource):
            logger.warning("Non-git scopes are currently not supported!")
            return

        source = cast(GitPolicyScopeSource, scope.policy)
        fetcher = GitPolicyFetcher(
            self._base_dir,
            scope_id,
            source,
            callbacks=NewCommitsCallbacks(
                base_dir=self._base_dir,
                scope_id=scope_id,
                source=source,
                http=self._http,
            ),
        )

        try:
            # using concurrent fetch so that if the celery worker is spawn with concurrency > 1,
            # the competing processes will not modify the same dir on the filesystem at the same time
            await fetcher.concurrent_fetch(
                redis=self._scopes.db.redis_connection,
                hinted_hash=hinted_hash,
                force_fetch=force_fetch,
            )
        except Exception as e:
            logger.exception(
                f"Could not fetch policy for scope {scope_id}, got error: {e}"
            )

    async def delete_scope(self, scope_id: str):
        logger.info(f"Delete scope: {scope_id}")
        scope = await self._scopes.get(scope_id)
        url = scope.policy.url

        scopes = await self._scopes.all()

        for scope in scopes:
            if scope.scope_id != scope_id and scope.policy.url == url:
                logger.info(
                    f"found another scope with same remote url: {scope.scope_id}"
                )
                return

        scope_dir = GitPolicyFetcher.repo_clone_path(
            self._base_dir, cast(GitPolicyScopeSource, scope.policy)
        )
        shutil.rmtree(scope_dir, ignore_errors=True)

    async def periodic_check(self):
        logger.info("Polling OPAL scopes for policy changes")
        scopes = await self._scopes.all()

        already_fetched = set()
        for scope in scopes:
            if scope.policy.poll_updates and scope.policy.url not in already_fetched:
                logger.info(
                    f"triggering sync_scope for scope {scope.scope_id} (remote: {scope.policy.url})"
                )
                sync_scope.delay(scope.scope_id, force_fetch=True)
                already_fetched.add(scope.policy.url)


def create_worker() -> Worker:
    opal_base_dir = Path(opal_server_config.BASE_DIR)

    worker = Worker(
        base_dir=opal_base_dir,
        scopes=ScopeRepository(RedisDB(opal_server_config.REDIS_URL)),
    )

    return worker


def with_worker(f):
    async def _inner(*args, **kwargs):
        async with create_worker() as worker:
            await f(worker, *args, **kwargs)

    return _inner


configure_logs()
app = Celery(
    "opal-worker",
    broker=opal_server_config.REDIS_URL,
    # if none, no results backend is used
    backend=opal_server_config.CELERY_BACKEND,
)
app.conf.task_default_queue = "opal-worker"
app.conf.task_serializer = "json"


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    polling_interval = opal_server_config.POLICY_REFRESH_INTERVAL
    if polling_interval == 0:
        logger.info("OPAL scopes: polling task is off.")
    else:
        logger.info(
            f"OPAL scopes: started polling task, interval is {polling_interval} seconds."
        )
        sender.add_periodic_task(polling_interval, periodic_check.s())


@app.task(ignore_result=True)
def sync_scope(
    scope_id: str, hinted_hash: Optional[str] = None, force_fetch: bool = False
):
    return async_to_sync(with_worker(Worker.sync_scope))(
        scope_id, hinted_hash=hinted_hash, force_fetch=force_fetch
    )


@app.task(ignore_result=True)
def delete_scope(scope_id: str):
    return async_to_sync(with_worker(Worker.delete_scope))(scope_id)


@app.task(ignore_result=True)
def periodic_check():
    return async_to_sync(with_worker(Worker.periodic_check))()


async def schedule_sync_all_scopes(scopes: ScopeRepository):
    """Syncing all scopes found in redis.

    Schedules separate sync scope tasks in celery. Git fetches are done
    only for unique remotes.
    """
    all_scopes = await scopes.all()
    logger.info(f"OPAL Scopes: syncing {len(all_scopes)} scopes in the background")

    already_fetched = set()
    already_synced_scope_ids: List[str] = []

    # first we sync with git fetch all the unique repositories
    for scope in all_scopes:
        if scope.policy.url not in already_fetched:
            logger.info(
                f"Sync scope {scope.scope_id} (force fetch, remote: {scope.policy.url})"
            )
            sync_scope.delay(scope.scope_id, force_fetch=True)
            already_fetched.add(scope.policy.url)
            already_synced_scope_ids.append(scope.scope_id)

    # then we sync other "same repo" scopes without git fetch to be more efficient
    for scope in all_scopes:
        if scope.scope_id not in already_synced_scope_ids:
            logger.info(
                f"Sync scope {scope.scope_id} (SKIP fetch, remote: {scope.policy.url})"
            )
            sync_scope.delay(scope.scope_id)
