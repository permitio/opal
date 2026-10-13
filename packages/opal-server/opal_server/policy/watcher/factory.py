from functools import partial
from pathlib import Path
from typing import Any, List, Optional

from fastapi_websocket_pubsub.pub_sub_server import PubSubEndpoint
from opal_common.confi.confi import load_conf_if_none
from opal_common.git_utils.repo_cloner import RepoClonePathFinder
from opal_common.logger import logger
from opal_common.sources.api_policy_source import ApiPolicySource
from opal_common.sources.git_policy_source import GitPolicySource
from opal_common.topics.publisher import TopicPublisher
from opal_server.config import (
    PolicySourceTypes,
    opal_server_config,
    validate_policy_bundle_source_mode,
)
from opal_server.policy.watcher.callbacks import publish_changed_directories
from opal_server.policy.watcher.manifest import get_policy_bundle_sources_registry
from opal_server.policy.watcher.task import (
    BasePolicyWatcherTask,
    MultiPolicyWatcherTask,
    PolicyWatcherTask,
)
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
    if (
        opal_server_config.POLICY_BUNDLE_MANIFEST_URL
        and source_type != PolicySourceTypes.Api
    ):
        raise ValueError("POLICY_BUNDLE_MANIFEST_URL requires API policy source type")

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
        validate_policy_bundle_source_mode(
            opal_server_config.POLICY_BUNDLE_SOURCES,
            opal_server_config.POLICY_BUNDLE_URL,
            opal_server_config.POLICY_BUNDLE_MANIFEST_URL,
        )
        if opal_server_config.POLICY_BUNDLE_MANIFEST_URL:

            def create_manifest_source(source_config):
                default_tmp_path = Path(opal_server_config.POLICY_BUNDLE_TMP_PATH)
                source = ApiPolicySource(
                    remote_source_url=source_config.url,
                    local_clone_path=source_config.clone_path
                    or str(
                        Path(opal_server_config.POLICY_REPO_CLONE_PATH)
                        / f"{opal_server_config.POLICY_REPO_CLONE_FOLDER_PREFIX}_{source_config.source_id}"
                    ),
                    polling_interval=(
                        polling_interval
                        if source_config.polling_interval is None
                        else source_config.polling_interval
                    ),
                    token=source_config.token or policy_bundle_token,
                    token_id=source_config.token_id
                    or load_conf_if_none(
                        policy_bundle_token_id,
                        opal_server_config.POLICY_BUNDLE_SERVER_TOKEN_ID,
                    ),
                    bundle_server_type=source_config.server_type
                    or load_conf_if_none(
                        policy_bundle_server_type,
                        opal_server_config.POLICY_BUNDLE_SERVER_TYPE,
                    ),
                    policy_bundle_path=source_config.tmp_path
                    or str(
                        default_tmp_path.with_name(
                            f"{default_tmp_path.stem}-{source_config.source_id}{default_tmp_path.suffix}"
                        )
                    ),
                    policy_bundle_git_add_pattern=source_config.git_add_pattern
                    or opal_server_config.POLICY_BUNDLE_GIT_ADD_PATTERN,
                    region=source_config.region
                    or load_conf_if_none(
                        policy_bundle_aws_region,
                        opal_server_config.POLICY_BUNDLE_SERVER_AWS_REGION,
                    ),
                    bundle_filename=source_config.filename,
                    source_id=source_config.source_id,
                )
                source.add_on_new_policy_callback(
                    partial(
                        publish_changed_directories,
                        publisher=publisher,
                        file_extensions=extensions,
                        bundle_ignore=bundle_ignore,
                        source_id=source_config.source_id,
                    )
                )
                return source

            return MultiPolicyWatcherTask(
                {},
                pubsub_endpoint,
                manifest_registry=get_policy_bundle_sources_registry(),
                source_factory=create_manifest_source,
            )

        if opal_server_config.POLICY_BUNDLE_SOURCES.sources:
            policy_sources = {}
            clone_paths = []
            tmp_paths = []
            for source_config in opal_server_config.POLICY_BUNDLE_SOURCES.sources:
                clone_path = source_config.clone_path or str(
                    Path(opal_server_config.POLICY_REPO_CLONE_PATH)
                    / f"{opal_server_config.POLICY_REPO_CLONE_FOLDER_PREFIX}_{source_config.source_id}"
                )
                default_tmp_path = Path(opal_server_config.POLICY_BUNDLE_TMP_PATH)
                tmp_path = source_config.tmp_path or str(
                    default_tmp_path.with_name(
                        f"{default_tmp_path.stem}-{source_config.source_id}{default_tmp_path.suffix}"
                    )
                )
                clone_paths.append(Path(clone_path).expanduser().resolve())
                tmp_paths.append(Path(tmp_path).expanduser().resolve())
                source_polling_interval = (
                    polling_interval
                    if source_config.polling_interval is None
                    else source_config.polling_interval
                )
                source_server_type = source_config.server_type or load_conf_if_none(
                    policy_bundle_server_type,
                    opal_server_config.POLICY_BUNDLE_SERVER_TYPE,
                )
                source_region = source_config.region or load_conf_if_none(
                    policy_bundle_aws_region,
                    opal_server_config.POLICY_BUNDLE_SERVER_AWS_REGION,
                )
                source = ApiPolicySource(
                    remote_source_url=source_config.url,
                    local_clone_path=clone_path,
                    polling_interval=source_polling_interval,
                    token=source_config.token or policy_bundle_token,
                    token_id=source_config.token_id
                    or load_conf_if_none(
                        policy_bundle_token_id,
                        opal_server_config.POLICY_BUNDLE_SERVER_TOKEN_ID,
                    ),
                    bundle_server_type=source_server_type,
                    policy_bundle_path=tmp_path,
                    policy_bundle_git_add_pattern=source_config.git_add_pattern
                    or opal_server_config.POLICY_BUNDLE_GIT_ADD_PATTERN,
                    region=source_region,
                    bundle_filename=source_config.filename,
                    source_id=source_config.source_id,
                )
                source.add_on_new_policy_callback(
                    partial(
                        publish_changed_directories,
                        publisher=publisher,
                        file_extensions=extensions,
                        bundle_ignore=bundle_ignore,
                        source_id=source_config.source_id,
                    )
                )
                policy_sources[source_config.source_id] = source
            if len(clone_paths) != len(set(clone_paths)):
                raise ValueError("API bundle sources must use distinct clone paths")
            if len(tmp_paths) != len(set(tmp_paths)):
                raise ValueError("API bundle sources must use distinct temporary paths")
            if any(
                clone_path == tmp_path
                or clone_path in tmp_path.parents
                or tmp_path in clone_path.parents
                for clone_path in clone_paths
                for tmp_path in tmp_paths
            ):
                raise ValueError(
                    "API bundle temporary paths must not be inside a source repository"
                )
            if any(
                left == right or left in right.parents or right in left.parents
                for index, left in enumerate(clone_paths)
                for right in clone_paths[index + 1 :]
            ):
                raise ValueError("API bundle source repositories must not overlap")
            return MultiPolicyWatcherTask(policy_sources, pubsub_endpoint)

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
