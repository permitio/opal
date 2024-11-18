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
        description="Local WebSocket URL for OPAL server. This is the endpoint that OPAL clients will connect to for real-time updates."
    )
    OPAL_WS_TOKEN = confi.str(
        "WS_TOKEN",
        "THIS_IS_A_DEV_SECRET",
        description="Authentication token for WebSocket connections. This token is used to secure the WebSocket connection between OPAL server and clients."
    )
    CLIENT_LOAD_LIMIT_NOTATION = confi.str(
        "CLIENT_LOAD_LIMIT_NOTATION",
        None,
        "Rate limit notation for the server's WebSocket endpoint. Format uses 'limits'-style notation (e.g., '10 per second'). "
        "This helps prevent server overload from too many client connections. "
        "See: https://limits.readthedocs.io/en/stable/quickstart.html#rate-limit-string-notation"
    )
    
    # The URL for the backbone pub/sub server (e.g. Postgres, Kafka, Redis) @see
    BROADCAST_URI = confi.str(
        "BROADCAST_URI",
        None,
        description="The URL for the backbone pub/sub server (e.g., Postgres, Kafka, Redis). "
        "This is used for broadcasting updates across multiple OPAL server instances, ensuring scalability and consistency."
    )
    BROADCAST_CHANNEL_NAME = confi.str(
        "BROADCAST_CHANNEL_NAME",
        "EventNotifier",
        description="Channel name for broadcast messages. This is used to segment messages in the backbone pub/sub system."
    )
    BROADCAST_CONN_LOSS_BUGFIX_EXPERIMENT_ENABLED = confi.bool(
        "BROADCAST_CONN_LOSS_BUGFIX_EXPERIMENT_ENABLED",
        True,
        description="Enable experimental fix for broadcast connection loss. This aims to improve reliability of the broadcast system."
    )

    # server security
    AUTH_PRIVATE_KEY_FORMAT = confi.enum(
        "AUTH_PRIVATE_KEY_FORMAT",
        EncryptionKeyFormat,
        EncryptionKeyFormat.pem,
        description="Format of the private key used for authentication. This key is used for signing JWTs for client authentication."
    )
    AUTH_PRIVATE_KEY_PASSPHRASE = confi.str(
        "AUTH_PRIVATE_KEY_PASSPHRASE",
        None,
        description="Passphrase for the private key used in authentication. Required if the private key is encrypted."
    )
    AUTH_PRIVATE_KEY = confi.delay(
        lambda AUTH_PRIVATE_KEY_FORMAT=None, AUTH_PRIVATE_KEY_PASSPHRASE="": confi.private_key(
            "AUTH_PRIVATE_KEY",
            default=None,
            key_format=AUTH_PRIVATE_KEY_FORMAT,
            passphrase=AUTH_PRIVATE_KEY_PASSPHRASE,
            description="Private key used for authentication. This is crucial for securing the OPAL server and client communication."
        )
    )
    AUTH_JWKS_URL = confi.str(
        "AUTH_JWKS_URL",
        "/.well-known/jwks.json",
        description="URL for JSON Web Key Set (JWKS). This is used for JWT validation in a distributed system."
    )
    AUTH_JWKS_STATIC_DIR = confi.str(
        "AUTH_JWKS_STATIC_DIR",
        os.path.join(os.getcwd(), "jwks_dir"),
        description="Directory for static JWKS files. Used when JWKS are stored locally rather than fetched from a URL."
    )
    AUTH_MASTER_TOKEN = confi.str(
        "AUTH_MASTER_TOKEN",
        None,
        description="Master token for authentication. This provides a high-level access token for administrative operations."
    )

    # policy source watcher
    POLICY_SOURCE_TYPE = confi.enum(
        "POLICY_SOURCE_TYPE",
        PolicySourceTypes,
        PolicySourceTypes.Git,
        description="Set your policy source. Can be GIT for Git repositories or API for API-based policy sources.",
    )
    POLICY_REPO_URL = confi.str(
        "POLICY_REPO_URL",
        None,
        description="URL of the Git repository hosting the policy. For example: https://github.com/permitio/opal-example-policy-repo.git. "
        "This is used when POLICY_SOURCE_TYPE is set to GIT.",
    )
    POLICY_BUNDLE_URL = confi.str(
        "POLICY_BUNDLE_URL",
        None,
        description="URL for the API-based policy bundle. This is used when POLICY_SOURCE_TYPE is set to API.",
    )
    POLICY_REPO_CLONE_PATH = confi.str(
        "POLICY_REPO_CLONE_PATH",
        os.path.join(os.getcwd(), "regoclone"),
        description="Base path to create local git folder for managing policy changes. OPAL will clone the policy repo to this location.",
    )
    POLICY_REPO_CLONE_FOLDER_PREFIX = confi.str(
        "POLICY_REPO_CLONE_FOLDER_PREFIX",
        "opal_repo_clone",
        description="Prefix for the local git folder. This helps identify OPAL-managed clones.",
    )
    POLICY_REPO_REUSE_CLONE_PATH = confi.bool(
        "POLICY_REPO_REUSE_CLONE_PATH",
        False,
        "Determines if OPAL server should use a fixed clone path and reuse it if it exists, instead of creating a new clone with a randomized suffix on each run.",
    )
    POLICY_REPO_MAIN_BRANCH = confi.str(
        "POLICY_REPO_MAIN_BRANCH",
        "master",
        description="The main branch of the policy repository to track. OPAL will watch this branch for policy updates."
    )
    POLICY_REPO_SSH_KEY = confi.str(
        "POLICY_REPO_SSH_KEY",
        None,
        description="SSH key for accessing private policy repositories. Required if the policy repo is not public."
    )
    POLICY_REPO_MANIFEST_PATH = confi.str(
        "POLICY_REPO_MANIFEST_PATH",
        "",
        "Path to the directory containing the '.manifest' file, or to the manifest file itself. "
        "The manifest file is used to specify which files in the repo should be treated as policies.",
    )
    POLICY_REPO_CLONE_TIMEOUT = confi.int(
        "POLICY_REPO_CLONE_TIMEOUT",
        0,
        description="Timeout in seconds for cloning the policy repository. 0 means wait indefinitely."
    )
    LEADER_LOCK_FILE_PATH = confi.str(
        "LEADER_LOCK_FILE_PATH",
        "/tmp/opal_server_leader.lock",
        description="Path to the leader lock file. Used in multi-server setups to determine the primary server."
    )
    POLICY_BUNDLE_SERVER_TYPE = confi.enum(
        "POLICY_BUNDLE_SERVER_TYPE",
        PolicyBundleServerType,
        PolicyBundleServerType.HTTP,
        description="The type of bundle server, e.g., basic HTTP or AWS S3. This affects how OPAL authenticates with the bundle server.",
    )
    POLICY_BUNDLE_SERVER_TOKEN = confi.str(
        "POLICY_BUNDLE_SERVER_TOKEN",
        None,
        description="Secret token to be sent to the API bundle server for authentication.",
    )
    POLICY_BUNDLE_SERVER_TOKEN_ID = confi.str(
        "POLICY_BUNDLE_SERVER_TOKEN_ID",
        None,
        description="The ID of the secret token to be sent to the API bundle server. Used in conjunction with POLICY_BUNDLE_SERVER_TOKEN.",
    )
    POLICY_BUNDLE_SERVER_AWS_REGION = confi.str(
        "POLICY_BUNDLE_SERVER_AWS_REGION",
        "us-east-1",
        description="The AWS region of the S3 bucket when using S3 as a bundle server.",
    )
    POLICY_BUNDLE_TMP_PATH = confi.str(
        "POLICY_BUNDLE_TMP_PATH",
        "/tmp/bundle.tar.gz",
        description="Temporary path for storing downloaded policy bundles. Ensure this path is writable.",
    )
    POLICY_BUNDLE_GIT_ADD_PATTERN = confi.str(
        "POLICY_BUNDLE_GIT_ADD_PATTERN",
        "*",
        description="File pattern to add files to git. Default is all files (*).",
    )

    REPO_WATCHER_ENABLED = confi.bool(
        "REPO_WATCHER_ENABLED",
        True,
        description="Enable or disable the repository watcher. When enabled, OPAL will actively watch for changes in the policy repository."
    )

    # publisher
    PUBLISHER_ENABLED = confi.bool(
        "PUBLISHER_ENABLED",
        True,
        description="Enable or disable the publisher. The publisher is responsible for broadcasting policy and data updates to clients."
    )

    # broadcaster keepalive
    BROADCAST_KEEPALIVE_INTERVAL = confi.int(
        "BROADCAST_KEEPALIVE_INTERVAL",
        3600,
        description="Time in seconds to wait between sending consecutive broadcaster keepalive messages. This helps maintain active connections.",
    )
    BROADCAST_KEEPALIVE_TOPIC = confi.str(
        "BROADCAST_KEEPALIVE_TOPIC",
        "__broadcast_session_keepalive__",
        description="The topic on which broadcaster keepalive messages are sent. This is used to maintain the pub/sub connection.",
    )

    # statistics
    MAX_CHANNELS_PER_CLIENT = confi.int(
        "MAX_CHANNELS_PER_CLIENT",
        15,
        description="Maximum number of channels per client for statistics tracking. After this number, new channels won't be added to statistics.",
    )
    STATISTICS_WAKEUP_CHANNEL = confi.str(
        "STATISTICS_WAKEUP_CHANNEL",
        "__opal_stats_wakeup",
        description="The topic a waking-up OPAL server uses to notify others it needs their statistics data.",
    )
    STATISTICS_STATE_SYNC_CHANNEL = confi.str(
        "STATISTICS_STATE_SYNC_CHANNEL",
        "__opal_stats_state_sync",
        description="The topic other servers use to provide their statistics state to a waking-up server.",
    )
    STATISTICS_SERVER_KEEPALIVE_CHANNEL = confi.str(
        "STATISTICS_SERVER_KEEPALIVE_CHANNEL",
        "__opal_stats_server_keepalive",
        description="The topic workers use to signal they exist and are alive. Part of the server health monitoring system.",
    )
    STATISTICS_SERVER_KEEPALIVE_TIMEOUT = confi.str(
        "STATISTICS_SERVER_KEEPALIVE_TIMEOUT",
        20,
        description="Timeout in seconds for forgetting a server from which a keep-alive hasn't been seen. Keep-alive frequency is half of this value.",
    )

    # Data updates
    ALL_DATA_TOPIC = confi.str(
        "ALL_DATA_TOPIC",
        DEFAULT_DATA_TOPIC,
        description="Top-level topic for all data updates. Clients subscribe to this topic to receive all data changes.",
    )
    ALL_DATA_ROUTE = confi.str(
        "ALL_DATA_ROUTE",
        "/policy-data",
        description="Route for accessing all policy data. This endpoint provides a complete snapshot of the current policy data."
    )
    ALL_DATA_URL = confi.str(
        "ALL_DATA_URL",
        confi.delay("http://localhost:7002{ALL_DATA_ROUTE}"),
        description="URL for fetching all data config. Used when all policy data is centralized in one location.",
    )
    DATA_CONFIG_ROUTE = confi.str(
        "DATA_CONFIG_ROUTE",
        "/data/config",
        description="URL to fetch the full basic configuration of data sources.",
    )
    DATA_CALLBACK_DEFAULT_ROUTE = confi.str(
        "DATA_CALLBACK_DEFAULT_ROUTE",
        "/data/callback_report",
        description="Default route for data update callbacks. Used if OPAL_DEFAULT_UPDATE_CALLBACKS is not set.",
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
        description="Configuration of data sources by topics. This defines how OPAL fetches and distributes policy data.",
    )

    DATA_UPDATE_TRIGGER_ROUTE = confi.str(
        "DATA_CONFIG_ROUTE",
        "/data/update",
        description="URL to trigger data update events. Used to manually initiate data updates.",
    )

    # Git service webhook (Default is Github)
    POLICY_REPO_WEBHOOK_SECRET = confi.str(
        "POLICY_REPO_WEBHOOK_SECRET",
        None,
        description="Secret for validating policy repo webhooks. This ensures that webhook calls are coming from a trusted source."
    )
    # The topic the event of the webhook will publish
    POLICY_REPO_WEBHOOK_TOPIC = "webhook"
    # Should we check the incoming webhook mentions the branch by name- and not just in the URL
    POLICY_REPO_WEBHOOK_ENFORCE_BRANCH: bool = confi.bool(
        "POLICY_REPO_WEBHOOK_ENFORCE_BRANCH",
        False,
        description="Enforce branch name check in webhook payload. When enabled, OPAL verifies that the webhook mentions the correct branch name."
    )
    # Parameters controlling how the incoming webhook should be read and processed
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
        description="Parameters for processing incoming webhooks from the policy repository. These settings define how OPAL interprets webhook payloads."
    )

    POLICY_REPO_POLLING_INTERVAL = confi.int(
        "POLICY_REPO_POLLING_INTERVAL",
        0,
        description="Interval in seconds for polling the policy repository. Set to 0 to disable polling. "
        "When set, OPAL will check for policy updates at this interval, useful when webhooks are not available."
    )

    ALLOWED_ORIGINS = confi.list(
        "ALLOWED_ORIGINS",
        ["*"],
        description="List of allowed origins for CORS (Cross-Origin Resource Sharing). Use '*' to allow all origins, or specify domains for more restrictive security."
    )
    FILTER_FILE_EXTENSIONS = confi.list(
        "FILTER_FILE_EXTENSIONS",
        [".rego", ".json"],
        description="File extensions to filter when processing policy files. OPAL will only consider files with these extensions as part of the policy."
    )
    BUNDLE_IGNORE = confi.list(
        "BUNDLE_IGNORE",
        [],
        description="List of patterns to ignore when creating policy bundles. Similar to .gitignore, this allows excluding certain files or directories from policy bundles."
    )

    NO_RPC_LOGS = confi.bool(
        "NO_RPC_LOGS",
        True,
        description="Disable RPC logs to reduce log verbosity. Set to False if you need detailed logging of RPC calls for debugging."
    )

    # client-api server
    SERVER_WORKER_COUNT = confi.int(
        "SERVER_WORKER_COUNT",
        None,
        description="Number of worker processes for the server. If not set, it defaults to the number of CPU cores. More workers can handle more concurrent requests."
    )

    SERVER_HOST = confi.str(
        "SERVER_HOST",
        "127.0.0.1",
        description="Address for the server to bind to. Use '0.0.0.0' to bind to all available network interfaces."
    )

    SERVER_PORT = confi.str(
        "SERVER_PORT",
        None,
        description="Deprecated. Use SERVER_BIND_PORT instead. Kept for backward compatibility."
    )

    SERVER_BIND_PORT = confi.int(
        "SERVER_BIND_PORT",
        7002,
        description="Port for the server to bind to. This is the port on which OPAL server will listen for incoming connections."
    )

    # optional APM tracing with datadog
    ENABLE_DATADOG_APM = confi.bool(
        "ENABLE_DATADOG_APM",
        False,
        description="Enable tracing with Datadog APM (Application Performance Monitoring). Useful for monitoring OPAL's performance in production environments."
    )

    # Scopes feature
    SCOPES = confi.bool(
        "SCOPES",
        default=False,
        description="Enable the scopes feature. Scopes allow for more granular control over policy and data distribution."
    )

    SCOPES_REPO_CLONES_SHARDS = confi.int(
        "SCOPES_REPO_CLONES_SHARDS",
        1,
        description="The maximum number of local clones to use for the same repo (reused across scopes). This helps in managing multiple scopes efficiently."
    )

    # Redis configuration
    REDIS_URL = confi.str(
        "REDIS_URL",
        default="redis://localhost",
        description="URL for Redis connection. Redis is used for caching and as a potential backbone for broadcasting updates."
    )

    # Base directory configuration
    BASE_DIR = confi.str(
        "BASE_DIR",
        default=pathlib.Path.home() / ".local/state/opal",
        description="Base directory for OPAL server files. This is where OPAL stores its state and temporary files."
    )

    # Policy refresh configuration
    POLICY_REFRESH_INTERVAL = confi.int(
        "POLICY_REFRESH_INTERVAL",
        default=0,
        description="Policy polling refresh interval in seconds. Set to 0 to disable periodic refreshes. This is useful for ensuring policies are up-to-date even without webhooks."
    )

    def on_load(self):
        if self.SERVER_PORT is not None and self.SERVER_PORT.isdigit():
            # Backward compatibility - if SERVER_PORT is set with a valid value, use it as SERVER_BIND_PORT
            self.SERVER_BIND_PORT = int(self.SERVER_PORT)


opal_server_config = OpalServerConfig(prefix="OPAL_")