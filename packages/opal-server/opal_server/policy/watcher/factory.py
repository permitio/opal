from functools import partial
from typing import Any, List, Optional

from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal_common.confi.confi import load_conf_if_none
from opal_common.git_utils.repo_cloner import RepoClonePathFinder
from opal_common.logger import logger
from opal_common.sources.api_policy_source import ApiPolicySource
from opal_common.sources.git_policy_source import GitPolicySource
from opal_common.topics.publisher import TopicPublisher
from opal_server.config import PolicySourceTypes, opal_server_config
from opal_server.policy.watcher.callbacks import publish_changed_directories
from opal_server.policy.watcher.task import BasePolicyWatcherTask, PolicyWatcherTask
from opal_server.scopes.task import ScopesPolicyWatcherTask


def setup_watcher_task(
    publisher: TopicPublisher,
    pubsub_endpoint: PubSubEndpoint,
    source_type: str = None,
    remote_source_url: str = None,
    clone_path_finder: RepoClonePathFinder = None,
    branch_name: str = None,
    ssh_key: Optional[str] = None,
    polling_interval: int = None,
    request_timeout: int = None,
    policy_bundle_token: str = None,
    policy_bundle_token_id: str = None,
    policy_bundle_server_type: str = None,
    policy_bundle_aws_region: str = None,
    extensions: Optional[List[str]] = None,
    bundle_ignore: Optional[List[str]] = None,
) -> BasePolicyWatcherTask:
    """Create a PolicyWatcherTask with Git / API policy source defined by env
    vars Load all the defaults from config if called without params.

    Args:
        publisher(TopicPublisher): server side publisher to publish changes in policy
        source_type(str): policy source type, can be Git / Api to opa bundle server
        remote_source_url(str): the base address to request the policy from
        clone_path_finder(RepoClonePathFinder): from which the local dir path for the repo clone would be retrieved
        branch_name(str):  name of remote branch in git to pull
        ssh_key (str, optional): private ssh key used to gain access to the cloned repo
        polling_interval(int):  how many seconds need to wait between polling
        request_timeout(int):  how many seconds need to wait until timeout
        policy_bundle_token(int):  auth token to include in connections to OPAL server. Defaults to POLICY_BUNDLE_SERVER_TOKEN.
        policy_bundle_token_id(int):  id token to include in connections to OPAL server. Defaults to POLICY_BUNDLE_SERVER_TOKEN_ID.
        policy_bundle_server_type (str): type of policy bundle server (HTTP S3). Defaults to POLICY_BUNDLE_SERVER_TYPE
        extensions(list(str), optional):  list of extantions to check when new policy arrive default is FILTER_FILE_EXTENSIONS
        bundle_ignore(list(str), optional):  list of glob paths to use for excluding files from bundle default is OPA_BUNDLE_IGNORE
    """
    if opal_server_config.SCOPES:
        return ScopesPolicyWatcherTask(pubsub_endpoint)

    # load defaults
    source_type = load_conf_if_none(source_type, opal_server_config.POLICY_SOURCE_TYPE)

    clone_path_finder = load_conf_if_none(
        clone_path_finder,
        RepoClonePathFinder(
            base_clone_path=opal_server_config.POLICY_REPO_CLONE_PATH,
            clone_subdirectory_prefix=opal_server_config.POLICY_REPO_CLONE_FOLDER_PREFIX,
            use_fixed_path=opal_server_config.POLICY_REPO_REUSE_CLONE_PATH,
        ),
    )

    clone_path = (
        clone_path_finder.get_clone_path() or clone_path_finder.create_new_clone_path()
    )
    logger.info(f"Policy repo will be cloned to: {clone_path}")

    branch_name = load_conf_if_none(
        branch_name, opal_server_config.POLICY_REPO_MAIN_BRANCH
    )
    ssh_key = load_conf_if_none(ssh_key, opal_server_config.POLICY_REPO_SSH_KEY)
    polling_interval = load_conf_if_none(
        polling_interval, opal_server_config.POLICY_REPO_POLLING_INTERVAL
    )
    request_timeout = load_conf_if_none(
        request_timeout, opal_server_config.POLICY_REPO_CLONE_TIMEOUT
    )
    policy_bundle_token = load_conf_if_none(
        policy_bundle_token, opal_server_config.POLICY_BUNDLE_SERVER_TOKEN
    )
    extensions = load_conf_if_none(
        extensions, opal_server_config.FILTER_FILE_EXTENSIONS
    )
    bundle_ignore = load_conf_if_none(bundle_ignore, opal_server_config.BUNDLE_IGNORE)
    if source_type == PolicySourceTypes.Git:
        remote_source_url = load_conf_if_none(
            remote_source_url, opal_server_config.POLICY_REPO_URL
        )
        if remote_source_url is None:
            logger.warning(
                "POLICY_REPO_URL is unset but repo watcher is enabled! disabling watcher."
            )
        watcher = GitPolicySource(
            remote_source_url=remote_source_url,
            local_clone_path=clone_path,
            branch_name=branch_name,
            ssh_key=ssh_key,
            polling_interval=polling_interval,
            request_timeout=request_timeout,
        )
    elif source_type == PolicySourceTypes.Api:
        remote_source_url = load_conf_if_none(
            remote_source_url, opal_server_config.POLICY_BUNDLE_URL
        )
        if remote_source_url is None:
            logger.warning(
                "POLICY_BUNDLE_URL is unset but policy watcher is enabled! disabling watcher."
            )
        policy_bundle_token_id = load_conf_if_none(
            policy_bundle_token_id, opal_server_config.POLICY_BUNDLE_SERVER_TOKEN_ID
        )
        policy_bundle_server_type = load_conf_if_none(
            policy_bundle_server_type, opal_server_config.POLICY_BUNDLE_SERVER_TYPE
        )
        policy_bundle_aws_region = load_conf_if_none(
            policy_bundle_aws_region, opal_server_config.POLICY_BUNDLE_SERVER_AWS_REGION
        )
        watcher = ApiPolicySource(
            remote_source_url=remote_source_url,
            local_clone_path=clone_path,
            polling_interval=polling_interval,
            token=policy_bundle_token,
            token_id=policy_bundle_token_id,
            bundle_server_type=policy_bundle_server_type,
            policy_bundle_path=opal_server_config.POLICY_BUNDLE_TMP_PATH,
            policy_bundle_git_add_pattern=opal_server_config.POLICY_BUNDLE_GIT_ADD_PATTERN,
            region=policy_bundle_aws_region,
        )
    else:
        raise ValueError("Unknown value for OPAL_POLICY_SOURCE_TYPE")
    watcher.add_on_new_policy_callback(
        partial(
            publish_changed_directories,
            publisher=publisher,
            file_extensions=extensions,
            bundle_ignore=bundle_ignore,
        )
    )
    return PolicyWatcherTask(watcher, pubsub_endpoint)
