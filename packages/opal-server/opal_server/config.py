import os
import pathlib
from enum import Enum

import yaml
from opal_common.authentication.casting import cast_private_key
from opal_common.authentication.types import EncryptionKeyFormat, PrivateKey
from opal_common.config import CommonStatisticsConfig, OpalCommonConfig, OpalSettings
from opal_common.schemas.data import DEFAULT_DATA_TOPIC, ServerDataSourceConfig
from opal_common.schemas.webhook import GitWebhookRequestParams
from pydantic import BaseSettings, Field, validator


class PolicySourceTypes(str, Enum):
    Git = "GIT"
    Api = "API"


class ServerRole(str, Enum):
    Primary = "primary"
    Secondary = "secondary"


class OpalServerConfig(OpalSettings):
    common: OpalCommonConfig = OpalCommonConfig()
    # ws server
    OPAL_WS_LOCAL_URL: str = "ws://localhost:7002/ws"
    OPAL_WS_TOKEN: str = "THIS_IS_A_DEV_SECRET"
    CLIENT_LOAD_LIMIT_NOTATION: str = Field(
        None,
        description="If supplied, rate limit would be enforced on server's websocket endpoint. "
        + "Format is `limits`-style notation (e.g '10 per second'), "
        + "see link: https://limits.readthedocs.io/en/stable/quickstart.html#rate-limit-string-notation",
    )

    class BroadcastConfig(OpalSettings):
        # The URL for the backbone pub/sub server (e.g. Postgres, Kfaka, Redis) @see
        BROADCAST_URI: str = None
        # The name to be used for segmentation in the backbone pub/sub (e.g. the Kafka topic)
        BROADCAST_CHANNEL_NAME: str = "EventNotifier"
        BROADCAST_CONN_LOSS_BUGFIX_EXPERIMENT_ENABLED: bool = True

        class BroadcastKeepaliveConfig(OpalSettings):
            # broadcaster keepalive
            BROADCAST_KEEPALIVE_INTERVAL: int = Field(
                3600,
                description="the time to wait between sending two consecutive broadcaster keepalive messages",
            )
            BROADCAST_KEEPALIVE_TOPIC: str = Field(
                "__broadcast_session_keepalive__",
                description="the topic on which we should send broadcaster keepalive messages",
            )

        keepalive: BroadcastKeepaliveConfig = BroadcastKeepaliveConfig()

    broadcast: BroadcastConfig = BroadcastConfig()

    class AuthConfig(OpalSettings):
        # server security
        AUTH_PRIVATE_KEY_FORMAT: EncryptionKeyFormat = EncryptionKeyFormat.pem
        AUTH_PRIVATE_KEY_PASSPHRASE: str = None

        AUTH_PRIVATE_KEY: PrivateKey = None

        @validator(
            "AUTH_PRIVATE_KEY", pre=True
        )  # pre=True to run before casting to PrivateKey
        def auth_private_key(cls, v, values):
            if v is not None:
                return cast_private_key(
                    v,
                    values["AUTH_PRIVATE_KEY_FORMAT"],
                    values["AUTH_PRIVATE_KEY_PASSPHRASE"],
                )

        AUTH_JWKS_URL: str = "/.well-known/jwks.json"
        AUTH_JWKS_STATIC_DIR: str = os.path.join(os.getcwd(), "jwks_dir")

        AUTH_MASTER_TOKEN: str = None

    auth: AuthConfig = AuthConfig()

    class PolicyConfig(OpalSettings):
        # policy source watcher
        POLICY_SOURCE_TYPE: PolicySourceTypes = Field(
            PolicySourceTypes.Git,
            description="Set your policy source can be GIT / API",
        )
        POLICY_REPO_URL: str = Field(
            None,
            description="Set your remote repo URL e.g:https://github.com/permitio/opal-example-policy-repo.git\
            , relevant only on GIT source type",
        )
        POLICY_BUNDLE_URL: str = Field(
            None,
            description="Set your API bundle URL, relevant only on API source type",
        )
        POLICY_REPO_CLONE_PATH: str = Field(
            os.path.join(os.getcwd(), "regoclone"),
            description="Base path to create local git folder inside it that manage policy change",
        )
        POLICY_REPO_CLONE_FOLDER_PREFIX: str = Field(
            "opal_repo_clone",
            description="Prefix for the local git folder",
        )
        POLICY_REPO_REUSE_CLONE_PATH: bool = Field(
            False,
            description="Set if OPAL server should use a fixed clone path (and reuse if it already exists) instead of randomizing its suffix on each run",
        )
        POLICY_REPO_MAIN_BRANCH: str = "master"
        POLICY_REPO_SSH_KEY: str = None
        POLICY_REPO_MANIFEST_PATH: str = Field(
            "",
            description="Path of the directory holding the '.manifest' file (new fashion), or of the manifest file itself (old fashion). Repo's root is used by default",
        )
        POLICY_REPO_CLONE_TIMEOUT: int = 0  # if 0, waits forever until successful clone

        POLICY_BUNDLE_SERVER_TOKEN: str = Field(
            None,
            description="Bearer token to sent to API bundle server",
        )
        POLICY_BUNDLE_TMP_PATH: str = Field(
            "/tmp/bundle.tar.gz",
            description="Path for temp policy file, need to be writeable",
        )
        POLICY_BUNDLE_GIT_ADD_PATTERN: str = Field(
            "*",
            description="File pattern to add files to git default to all the files (*)",
        )

        REPO_WATCHER_ENABLED: bool = True

        POLICY_REPO_POLLING_INTERVAL: int = 0

        class PolicyRepoWebhookConfig(OpalSettings):
            # Git service webhook (Default is Github)
            POLICY_REPO_WEBHOOK_SECRET: str = None
            # The topic the event of the webhook will publish
            POLICY_REPO_WEBHOOK_TOPIC = "webhook"
            # Should we check the incoming webhook mentions the branch by name- and not just in the URL
            POLICY_REPO_WEBHOOK_ENFORCE_BRANCH: bool = False
            # Parameters controlling how the incoming webhook should be read and processed
            POLICY_REPO_WEBHOOK_PARAMS: GitWebhookRequestParams = (
                GitWebhookRequestParams(
                    secret_header_name="x-hub-signature-256",
                    secret_type="signature",
                    secret_parsing_regex="sha256=(.*)",
                    event_header_name="X-GitHub-Event",
                    event_request_key=None,
                    push_event_value="push",
                )
            )

        repo_webhook: PolicyRepoWebhookConfig = PolicyRepoWebhookConfig()

        FILTER_FILE_EXTENSIONS: list = [".rego", ".json"]

        BUNDLE_IGNORE: list = []

    policy: PolicyConfig = PolicyConfig()

    LEADER_LOCK_FILE_PATH: str = "/tmp/opal_server_leader.lock"

    # publisher
    PUBLISHER_ENABLED: bool = True

    # statistics
    MAX_CHANNELS_PER_CLIENT: int = Field(
        15,
        description="max number of records per client, after this number it will not be added to statistics, relevant only if STATISTICS_ENABLED",
    )

    class ServerStatisticsConfig(CommonStatisticsConfig):
        STATISTICS_WAKEUP_CHANNEL: str = Field(
            "__opal_stats_wakeup",
            description="The topic a waking-up OPAL server uses to notify others he needs their statistics data",
        )
        STATISTICS_STATE_SYNC_CHANNEL: str = Field(
            "__opal_stats_state_sync",
            description="The topic other servers with statistics provide their state to a waking-up server",
        )

    # TODO: Should this somehow extend OpalCommonConfig.statistics? (to share with client)
    statistics: ServerStatisticsConfig = ServerStatisticsConfig()

    class DataConfig(OpalSettings):
        # Data updates
        ALL_DATA_TOPIC: str = Field(
            DEFAULT_DATA_TOPIC, description="Top level topic for data"
        )
        ALL_DATA_ROUTE: str = "/policy-data"
        ALL_DATA_URL: str = Field(
            None,
            description="URL for all data config [If you choose to have it all at one place]",
        )

        @validator("ALL_DATA_URL", pre=True)
        def all_data_url(cls, v, values):
            if v is None:
                return f"http://localhost:7002{values['ALL_DATA_ROUTE']}"
            return v

        DATA_CONFIG_ROUTE: str = Field(
            "/data/config",
            description="URL to fetch the full basic configuration of data",
        )
        DATA_CALLBACK_DEFAULT_ROUTE: str = Field(
            "/data/callback_report",
            description="Exists as a sane default in case the user did not set OPAL_DEFAULT_UPDATE_CALLBACKS",
        )

        DATA_CONFIG_SOURCES: ServerDataSourceConfig = Field(
            None,
            description="Configuration of data sources by topics",
        )

        @validator("DATA_CONFIG_SOURCES", pre=True)
        def data_config_sources(cls, v, values):
            if v is None:
                return ServerDataSourceConfig(
                    config={
                        "entries": [
                            {
                                "url": values["ALL_DATA_URL"],
                                "topics": [values["ALL_DATA_TOPIC"]],
                            }
                        ]
                    }
                )
            return v

        DATA_UPDATE_TRIGGER_ROUTE: str = Field(
            "/data/update",
            description="URL to trigger data update events",
        )

    data: DataConfig = DataConfig()

    ALLOWED_ORIGINS: list = ["*"]

    NO_RPC_LOGS: bool = True

    # client-api server
    SERVER_WORKER_COUNT: int = Field(
        None,
        description="(if run via CLI) Worker count for the server [Default calculated to CPU-cores]",
    )

    SERVER_HOST: str = Field(
        "127.0.0.1",
        description="(if run via CLI)  Address for the server to bind",
    )

    SERVER_PORT: str = Field(
        None,
        # Users have expirienced errors when kubernetes sets the envar OPAL_SERVER_PORT="tcp://..." (which fails to parse as a port integer).
        description="Deprecated, use SERVER_BIND_PORT instead",
    )

    SERVER_BIND_PORT: int = Field(
        7002,
        description="(if run via CLI)  Port for the server to bind",
    )

    # optional APM tracing with datadog
    ENABLE_DATADOG_APM: bool = Field(
        False,
        description="Set if OPAL server should enable tracing with datadog APM",
    )

    REDIS_URL: str = "redis://localhost"

    BASE_DIR: str = str(pathlib.Path.home() / ".local/state/opal")

    class ScopesConfig(OpalSettings):
        SCOPES: bool = False

        POLICY_REFRESH_INTERVAL: int = Field(
            0,
            description="Policy polling refresh interval",
        )

    scopes: ScopesConfig = ScopesConfig()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.SERVER_PORT is not None and self.SERVER_PORT.isdigit():
            # Backward compatibility - if SERVER_PORT is set with a valid value, use it as SERVER_BIND_PORT
            self.SERVER_BIND_PORT = int(self.SERVER_PORT)


# TODO:
# 1. Share with client
# 2. Should path be configurable from envars?
# 3. What about common?
with open("/opal/config.yaml", "r") as config_stream:
    try:
        config_data = yaml.safe_load(config_stream)
        opal_server_config = OpalServerConfig.parse_obj(config_data["server"])
    except yaml.YAMLError as exc:
        print(exc)
        exit(1)
