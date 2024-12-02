import os
import pathlib
from enum import Enum

from opal_common.authentication.types import EncryptionKeyFormat
from opal_common.confi import Confi
from opal_common.schemas.data import DEFAULT_DATA_TOPIC, ServerDataSourceConfig
from opal_common.schemas.webhook import GitWebhookRequestParams

confi = Confi(prefix="OPAL_")


class PolicySourceTypes(str, Enum):
    Git = "GIT"
    Api = "API"


class PolicyBundleServerType(str, Enum):
    HTTP = "HTTP"
    AWS_S3 = "AWS-S3"


class ServerRole(str, Enum):
    Primary = "primary"
    Secondary = "secondary"


class OpalServerConfig(Confi):
    # ws server
    OPAL_WS_LOCAL_URL = confi.str(
        "WS_LOCAL_URL",
        "ws://localhost:7002/ws",
        description="The local WebSocket URL for OPAL",
    )
    OPAL_WS_TOKEN = confi.str(
        "WS_TOKEN", "THIS_IS_A_DEV_SECRET", description="The WebSocket token for OPAL"
    )
    CLIENT_LOAD_LIMIT_NOTATION = confi.str(
        "CLIENT_LOAD_LIMIT_NOTATION",
        None,
        description="If supplied, rate limit would be enforced on server's websocket endpoint. "
        + "Format is `limits`-style notation (e.g '10 per second'), "
        + "see link: https://limits.readthedocs.io/en/stable/quickstart.html#rate-limit-string-notation",
    )
    # The URL for the backbone pub/sub server (e.g. Postgres, Kfaka, Redis) @see
    BROADCAST_URI = confi.str(
        "BROADCAST_URI", None, description="The URL for the backbone pub/sub server"
    )
    # The name to be used for segmentation in the backbone pub/sub (e.g. the Kafka topic)
    BROADCAST_CHANNEL_NAME = confi.str(
        "BROADCAST_CHANNEL_NAME",
        "EventNotifier",
        description="The name to be used for segmentation in the backbone pub/sub",
    )
    BROADCAST_CONN_LOSS_BUGFIX_EXPERIMENT_ENABLED = confi.bool(
        "BROADCAST_CONN_LOSS_BUGFIX_EXPERIMENT_ENABLED",
        True,
        description="Enable experimental bugfix for broadcast connection loss",
    )

    # server security
    AUTH_PRIVATE_KEY_FORMAT = confi.enum(
        "AUTH_PRIVATE_KEY_FORMAT",
        EncryptionKeyFormat,
        EncryptionKeyFormat.pem,
        description="The format of the private key for authentication",
    )
    AUTH_PRIVATE_KEY_PASSPHRASE = confi.str(
        "AUTH_PRIVATE_KEY_PASSPHRASE",
        None,
        description="The passphrase for the private key",
    )

    AUTH_PRIVATE_KEY = confi.delay(
        lambda AUTH_PRIVATE_KEY_FORMAT=None, AUTH_PRIVATE_KEY_PASSPHRASE="": confi.private_key(
            "AUTH_PRIVATE_KEY",
            default=None,
            key_format=AUTH_PRIVATE_KEY_FORMAT,
            passphrase=AUTH_PRIVATE_KEY_PASSPHRASE,
            description="The private key for authentication",
        )
    )

    AUTH_JWKS_URL = confi.str(
        "AUTH_JWKS_URL",
        "/.well-known/jwks.json",
        description="The URL for the JSON Web Key Set (JWKS)",
    )
    AUTH_JWKS_STATIC_DIR = confi.str(
        "AUTH_JWKS_STATIC_DIR",
        os.path.join(os.getcwd(), "jwks_dir"),
        description="The directory for static JWKS files",
    )

    AUTH_MASTER_TOKEN = confi.str(
        "AUTH_MASTER_TOKEN", None, description="The master token for authentication"
    )

    # policy source watcher
    POLICY_SOURCE_TYPE = confi.enum(
        "POLICY_SOURCE_TYPE",
        PolicySourceTypes,
        PolicySourceTypes.Git,
        description="Set your policy source can be GIT / API",
    )
    POLICY_REPO_URL = confi.str(
        "POLICY_REPO_URL",
        None,
        description="Set your remote repo URL e.g:https://github.com/permitio/opal-example-policy-repo.git\
        , relevant only on GIT source type",
    )
    POLICY_BUNDLE_URL = confi.str(
        "POLICY_BUNDLE_URL",
        None,
        description="Set your API bundle URL, relevant only on API source type",
    )
    POLICY_REPO_CLONE_PATH = confi.str(
        "POLICY_REPO_CLONE_PATH",
        os.path.join(os.getcwd(), "regoclone"),
        description="Base path to create local git folder inside it that manage policy change",
    )
    POLICY_REPO_CLONE_FOLDER_PREFIX = confi.str(
        "POLICY_REPO_CLONE_FOLDER_PREFIX",
        "opal_repo_clone",
        description="Prefix for the local git folder",
    )
    POLICY_REPO_REUSE_CLONE_PATH = confi.bool(
        "POLICY_REPO_REUSE_CLONE_PATH",
        False,
        description="Set if OPAL server should use a fixed clone path (and reuse if it already exists) instead of randomizing its suffix on each run",
    )
    POLICY_REPO_MAIN_BRANCH = confi.str(
        "POLICY_REPO_MAIN_BRANCH",
        "master",
        description="The main branch of the policy repository",
    )
    POLICY_REPO_SSH_KEY = confi.str(
        "POLICY_REPO_SSH_KEY", None, description="The SSH key for the policy repository"
    )
    POLICY_REPO_MANIFEST_PATH = confi.str(
        "POLICY_REPO_MANIFEST_PATH",
        "",
        description="Path of the directory holding the '.manifest' file (new fashion), or of the manifest file itself (old fashion). Repo's root is used by default",
    )
    POLICY_REPO_CLONE_TIMEOUT = confi.int(
        "POLICY_REPO_CLONE_TIMEOUT",
        0,
        description="The timeout for cloning the policy repository (0 means wait forever)",
    )
    LEADER_LOCK_FILE_PATH = confi.str(
        "LEADER_LOCK_FILE_PATH",
        "/tmp/opal_server_leader.lock",
        description="The path to the leader lock file",
    )
    POLICY_BUNDLE_SERVER_TYPE = confi.enum(
        "POLICY_BUNDLE_SERVER_TYPE",
        PolicyBundleServerType,
        PolicyBundleServerType.HTTP,
        description="The type of bundle server e.g. basic HTTP , AWS S3. (affects how we authenticate with it)",
    )
    POLICY_BUNDLE_SERVER_TOKEN = confi.str(
        "POLICY_BUNDLE_SERVER_TOKEN",
        None,
        description="Secret token to be sent to API bundle server",
    )
    POLICY_BUNDLE_SERVER_TOKEN_ID = confi.str(
        "POLICY_BUNDLE_SERVER_TOKEN_ID",
        None,
        description="The id of the secret token to be sent to API bundle server",
    )
    POLICY_BUNDLE_SERVER_AWS_REGION = confi.str(
        "POLICY_BUNDLE_SERVER_AWS_REGION",
        "us-east-1",
        description="The AWS region of the S3 bucket",
    )
    POLICY_BUNDLE_TMP_PATH = confi.str(
        "POLICY_BUNDLE_TMP_PATH",
        "/tmp/bundle.tar.gz",
        description="Path for temp policy file, need to be writeable",
    )
    POLICY_BUNDLE_GIT_ADD_PATTERN = confi.str(
        "POLICY_BUNDLE_GIT_ADD_PATTERN",
        "*",
        description="File pattern to add files to git default to all the files (*)",
    )

    REPO_WATCHER_ENABLED = confi.bool(
        "REPO_WATCHER_ENABLED", True, description="Enable the repository watcher"
    )

    # publisher
    PUBLISHER_ENABLED = confi.bool(
        "PUBLISHER_ENABLED", True, description="Enable the publisher"
    )

    # broadcaster keepalive
    BROADCAST_KEEPALIVE_INTERVAL = confi.int(
        "BROADCAST_KEEPALIVE_INTERVAL",
        3600,
        description="the time to wait between sending two consecutive broadcaster keepalive messages",
    )
    BROADCAST_KEEPALIVE_TOPIC = confi.str(
        "BROADCAST_KEEPALIVE_TOPIC",
        "__broadcast_session_keepalive__",
        description="the topic on which we should send broadcaster keepalive messages",
    )

    # statistics
    MAX_CHANNELS_PER_CLIENT = confi.int(
        "MAX_CHANNELS_PER_CLIENT",
        15,
        description="max number of records per client, after this number it will not be added to statistics, relevant only if STATISTICS_ENABLED",
    )
    STATISTICS_WAKEUP_CHANNEL = confi.str(
        "STATISTICS_WAKEUP_CHANNEL",
        "__opal_stats_wakeup",
        description="The topic a waking-up OPAL server uses to notify others he needs their statistics data",
    )
    STATISTICS_STATE_SYNC_CHANNEL = confi.str(
        "STATISTICS_STATE_SYNC_CHANNEL",
        "__opal_stats_state_sync",
        description="The topic other servers with statistics provide their state to a waking-up server",
    )
    STATISTICS_SERVER_KEEPALIVE_CHANNEL = confi.str(
        "STATISTICS_SERVER_KEEPALIVE_CHANNEL",
        "__opal_stats_server_keepalive",
        description="The topic workers use to signal they exist and are alive",
    )
    STATISTICS_SERVER_KEEPALIVE_TIMEOUT = confi.str(
        "STATISTICS_SERVER_KEEPALIVE_TIMEOUT",
        20,
        description="Timeout for forgetting a server from which a keep-alive haven't been seen (keep-alive frequency would be half of this value)",
    )

    # Data updates
    ALL_DATA_TOPIC = confi.str(
        "ALL_DATA_TOPIC",
        DEFAULT_DATA_TOPIC,
        description="Top level topic for data",
    )
    ALL_DATA_ROUTE = confi.str(
        "ALL_DATA_ROUTE", "/policy-data", description="The route for all policy data"
    )
    ALL_DATA_URL = confi.str(
        "ALL_DATA_URL",
        confi.delay("http://localhost:7002{ALL_DATA_ROUTE}"),
        description="URL for all data config [If you choose to have it all at one place]",
    )
    DATA_CONFIG_ROUTE = confi.str(
        "DATA_CONFIG_ROUTE",
        "/data/config",
        description="URL to fetch the full basic configuration of data",
    )
    DATA_CALLBACK_DEFAULT_ROUTE = confi.str(
        "DATA_CALLBACK_DEFAULT_ROUTE",
        "/data/callback_report",
        description="Exists as a sane default in case the user did not set OPAL_DEFAULT_UPDATE_CALLBACKS",
    )

    DATA_CONFIG_SOURCES = confi.model(
        "DATA_CONFIG_SOURCES",
        ServerDataSourceConfig,
        confi.delay(
            lambda ALL_DATA_URL="", ALL_DATA_TOPIC="": {
                "config": {
                    "entries": [{"url": ALL_DATA_URL, "topics": [ALL_DATA_TOPIC]}]
                }
            }
        ),
        description="Configuration of data sources by topics",
    )

    DATA_UPDATE_TRIGGER_ROUTE = confi.str(
        "DATA_CONFIG_ROUTE",
        "/data/update",
        description="URL to trigger data update events",
    )

    # Git service webhook (Default is Github)
    POLICY_REPO_WEBHOOK_SECRET = confi.str(
        "POLICY_REPO_WEBHOOK_SECRET",
        None,
        description="The secret for the policy repository webhook",
    )
    # The topic the event of the webhook will publish
    POLICY_REPO_WEBHOOK_TOPIC = "webhook"
    # Should we check the incoming webhook mentions the branch by name- and not just in the URL
    POLICY_REPO_WEBHOOK_ENFORCE_BRANCH: bool = confi.bool(
        "POLICY_REPO_WEBHOOK_ENFORCE_BRANCH",
        False,
        description="Enforce branch name in incoming webhook",
    )
    # Parameters controlling how the incoming webhook should be read and processed
    POLICY_REPO_WEBHOOK_PARAMS: GitWebhookRequestParams = confi.model(
        "POLICY_REPO_WEBHOOK_PARAMS",
        GitWebhookRequestParams,
        {
            "secret_header_name": "x-hub-signature-256",
            "secret_type": "signature",
            "secret_parsing_regex": "sha256=(.*)",
            "event_header_name": "X-GitHub-Event",
            "event_request_key": None,
            "push_event_value": "push",
        },
        description="Parameters for processing the incoming webhook",
    )

    POLICY_REPO_POLLING_INTERVAL = confi.int(
        "POLICY_REPO_POLLING_INTERVAL",
        0,
        description="The polling interval for the policy repository",
    )

    ALLOWED_ORIGINS = confi.list(
        "ALLOWED_ORIGINS", ["*"], description="List of allowed origins for CORS"
    )
    FILTER_FILE_EXTENSIONS = confi.list(
        "FILTER_FILE_EXTENSIONS",
        [".rego", ".json"],
        description="List of file extensions to filter. Example: ['.rego', '.json']",
    )
    BUNDLE_IGNORE = confi.list(
        "BUNDLE_IGNORE", [], description="List of patterns to ignore in the bundle"
    )

    NO_RPC_LOGS = confi.bool("NO_RPC_LOGS", True, description="Disable RPC logs")

    # client-api server
    SERVER_WORKER_COUNT = confi.int(
        "SERVER_WORKER_COUNT",
        None,
        description="(if run via CLI) Worker count for the server [Default calculated to CPU-cores]",
    )

    SERVER_HOST = confi.str(
        "SERVER_HOST",
        "127.0.0.1",
        description="(if run via CLI)  Address for the server to bind",
    )

    SERVER_PORT = confi.str(
        "SERVER_PORT",
        None,
        # Users have experienced errors when kubernetes sets the env-var OPAL_SERVER_PORT="tcp://..." (which fails to parse as a port integer).
        description="Deprecated, use SERVER_BIND_PORT instead",
    )

    SERVER_BIND_PORT = confi.int(
        "SERVER_BIND_PORT",
        7002,
        description="(if run via CLI)  Port for the server to bind",
    )

    # optional APM tracing with datadog
    ENABLE_DATADOG_APM = confi.bool(
        "ENABLE_DATADOG_APM",
        False,
        description="Set if OPAL server should enable tracing with datadog APM",
    )

    SCOPES = confi.bool("SCOPES", default=False, description="Enable scopes")

    SCOPES_REPO_CLONES_SHARDS = confi.int(
        "SCOPES_REPO_CLONES_SHARDS",
        1,
        description="The max number of local clones to use for the same repo (reused across scopes)",
    )

    REDIS_URL = confi.str(
        "REDIS_URL",
        default="redis://localhost",
        description="The URL for the Redis server",
    )

    BASE_DIR = confi.str(
        "BASE_DIR",
        default=pathlib.Path.home() / ".local/state/opal",
        description="The base directory for OPAL",
    )

    POLICY_REFRESH_INTERVAL = confi.int(
        "POLICY_REFRESH_INTERVAL",
        default=0,
        description="Policy polling refresh interval",
    )

    def on_load(self):
        if self.SERVER_PORT is not None and self.SERVER_PORT.isdigit():
            # Backward compatibility - if SERVER_PORT is set with a valid value, use it as SERVER_BIND_PORT
            self.SERVER_BIND_PORT = int(self.SERVER_PORT)


opal_server_config = OpalServerConfig(prefix="OPAL_")
