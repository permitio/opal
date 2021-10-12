from typing import Any, Optional, List
from functools import partial

from fastapi_websocket_pubsub import Topic
from opal_common.logger import logger
from opal_common.sources.api_policy_source import ApiPolicySource
from opal_common.sources.git_policy_source import GitPolicySource
from opal_common.topics.publisher import TopicPublisher
from opal_server.config import PolicySourceTypes, opal_server_config
from opal_server.policy.watcher.task import PolicyWatcherTask
from opal_server.policy.watcher.callbacks import publish_changed_directories


def setup_watcher_task(
    publisher: TopicPublisher,
    source_type: str = None,
    remote_source_url: str = None,
    clone_path: str = None,
    branch_name: str = None,
    ssh_key: Optional[str] = None,
    polling_interval: int = None,
    request_timeout: int = None,
    policy_bundle_token: str = None,
    extensions: Optional[List[str]] = None,
) -> PolicyWatcherTask:
    """
        Create a PolicyWatcherTask with Git / API policy source defined by env vars
        Load all the defaults from config if called without params

        Args:
            publisher(TopicPublisher): server side publisher to publish changes in policy
            source_type(str): policy source type, can be Git / Api to opa bundle server
            remote_source_url(str): the base address to request the policy from
            clone_path(str):  path for the local git to manage policies
            branch_name(str):  name of remote branch in git to pull
            ssh_key (str, optional): private ssh key used to gain access to the cloned repo
            polling_interval(int):  how much seconds need to wait between polling
            request_timeout(int):  how much seconds need to wait until timout
            policy_bundle_token(int):  auth token to include in connections to OPAL server. Defaults to POLICY_BUNDLE_SERVER_TOKEN.
            extensions(list(str), optional):  list of extantions to check when new policy arrive default is OPA_FILE_EXTENSIONS

    """
    # load defaults
    source_type = source_type or opal_server_config.POLICY_SOURCE_TYPE
    remote_source_url = remote_source_url or opal_server_config.POLICY_REPO_URL
    clone_path = clone_path or opal_server_config.POLICY_REPO_CLONE_PATH
    branch_name = branch_name or opal_server_config.POLICY_REPO_MAIN_BRANCH
    ssh_key = ssh_key or opal_server_config.POLICY_REPO_SSH_KEY
    polling_interval = polling_interval or opal_server_config.POLICY_REPO_POLLING_INTERVAL
    request_timeout = request_timeout or opal_server_config.POLICY_REPO_CLONE_TIMEOUT
    policy_bundle_token = policy_bundle_token or opal_server_config.POLICY_BUNDLE_SERVER_TOKEN
    extensions = extensions if extensions is not None else opal_server_config.OPA_FILE_EXTENSIONS
    if source_type == PolicySourceTypes.Git.value:
        watcher = GitPolicySource(
            remote_source_url=remote_source_url,
            local_clone_path=clone_path,
            branch_name=branch_name,
            ssh_key=ssh_key,
            polling_interval=polling_interval,
            request_timeout=request_timeout
        )
    elif source_type == PolicySourceTypes.Api.value:
        watcher = ApiPolicySource(
            remote_source_url=remote_source_url,
            local_clone_path=clone_path,
            polling_interval=polling_interval,
            token=policy_bundle_token
        )
    else:
        raise ValueError("Unknown value for OPAL_POLICY_SOURCE_TYPE")
    watcher.add_on_new_policy_callback(
        partial(
            publish_changed_directories,
            publisher=publisher,
            file_extensions=extensions
        )
    )
    return PolicyWatcherTask(watcher)


async def trigger_repo_watcher_pull(watcher: PolicyWatcherTask, topic: Topic, data: Any):
    """
    triggers the policy watcher check for changes.
    will trigger a task on the watcher's thread.
    """
    logger.info("webhook listener triggered")
    watcher.trigger()