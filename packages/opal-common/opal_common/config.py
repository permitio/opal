from pathlib import Path
from sys import prefix

from opal_common.authentication.types import EncryptionKeyFormat, JWTAlgorithm
from opal_common.confi import Confi, confi

_LOG_FORMAT_WITHOUT_PID = "<green>{time}</green> | <blue>{name: <40}</blue>|<level>{level:^6} | {message}</level>\n{exception}"
_LOG_FORMAT_WITH_PID = "<green>{time}</green> | {process} | <blue>{name: <40></blue>|<level>{level:^6} | {message}</level>\n{exception}"


class OpalCommonConfig(Confi):
    ALLOWED_ORIGINS = confi.list(
        "ALLOWED_ORIGINS", 
        ["*"], 
        description="List of allowed origins for CORS. Use ['*'] to allow all origins, or specify a list of trusted domains for enhanced security in production environments."
    )
    # Process name to show in logs - Not confi-controlable on purpose
    PROCESS_NAME = ""
    # Logging
    # - Log formatting
    LOG_FORMAT_INCLUDE_PID = confi.bool(
        "LOG_FORMAT_INCLUDE_PID", 
        False, 
        description="Include process ID in log format. Useful for distinguishing between multiple OPAL processes in a distributed setup."
    )
    LOG_FORMAT = confi.str(
        "LOG_FORMAT",
        confi.delay(
            lambda LOG_FORMAT_INCLUDE_PID=False: (
                _LOG_FORMAT_WITH_PID
                if LOG_FORMAT_INCLUDE_PID
                else _LOG_FORMAT_WITHOUT_PID
            )
        ),
        description="The format of the log messages. Automatically adjusts based on LOG_FORMAT_INCLUDE_PID setting.",
    )
    LOG_TRACEBACK = confi.bool(
        "LOG_TRACEBACK", 
        True, 
        description="Include traceback in log messages. Helpful for debugging but may increase log verbosity."
    )
    LOG_DIAGNOSE = confi.bool(
        "LOG_DIAGNOSE", 
        True, 
        description="Include diagnosis in log messages. Provides additional context for troubleshooting."
    )
    LOG_COLORIZE = confi.bool(
        "LOG_COLORIZE", 
        True, 
        description="Colorize log messages for improved readability in terminal output."
    )
    LOG_SERIALIZE = confi.bool(
        "LOG_SERIALIZE", 
        False, 
        description="Serialize log messages to JSON format. Useful for log aggregation and analysis tools."
    )
    LOG_SHOW_CODE_LINE = confi.bool(
        "LOG_SHOW_CODE_LINE", 
        True, 
        description="Show code line in log messages. Aids in pinpointing the exact location of logged events in the source code."
    )
    #  - log level
    LOG_LEVEL = confi.str(
        "LOG_LEVEL", 
        "INFO", 
        description="The log level to show. Options: DEBUG, INFO, WARNING, ERROR, CRITICAL. Adjust based on desired verbosity and environment (e.g., DEBUG for development, INFO or WARNING for production)."
    )
    #  - Which modules should be logged
    LOG_MODULE_EXCLUDE_LIST = confi.list(
        "LOG_MODULE_EXCLUDE_LIST",
        [
            "uvicorn",
            # NOTE: the env var LOG_MODULE_EXCLUDE_OPA affects this list
        ],
        description="List of modules to exclude from logging. Use this to reduce noise from well-behaved third-party libraries."
    )
    LOG_MODULE_INCLUDE_LIST = confi.list(
        "LOG_MODULE_INCLUDE_LIST",
        ["uvicorn.protocols.http"],
        description="List of modules to include in logging. Overrides LOG_MODULE_EXCLUDE_LIST for specific modules you want to monitor closely."
    )
    LOG_PATCH_UVICORN_LOGS = confi.bool(
        "LOG_PATCH_UVICORN_LOGS",
        True,
        description="Should we takeover UVICORN's logs so they appear in the main logger. Enables consistent logging format across OPAL and its web server."
    )
    # - Log to file as well ( @see https://github.com/Delgan/loguru#easier-file-logging-with-rotation--retention--compression)
    LOG_TO_FILE = confi.bool(
        "LOG_TO_FILE", 
        False, 
        description="Enable logging to a file in addition to console output. Useful for persistent logs and post-mortem analysis."
    )
    LOG_FILE_PATH = confi.str(
        "LOG_FILE_PATH",
        f"opal_{PROCESS_NAME}{{time}}.log",
        description="Path to save log file. Supports time-based formatting for log rotation."
    )
    LOG_FILE_ROTATION = confi.str(
        "LOG_FILE_ROTATION", 
        "250 MB", 
        description="Log file rotation size. Helps manage disk space by creating new log files when the current one reaches this size."
    )
    LOG_FILE_RETENTION = confi.str(
        "LOG_FILE_RETENTION", 
        "10 days", 
        description="Log file retention time. Automatically removes old log files to prevent disk space issues."
    )
    LOG_FILE_COMPRESSION = confi.str(
        "LOG_FILE_COMPRESSION", 
        None, 
        description="Log file compression format. Set to 'gz' or 'zip' to compress rotated logs and save disk space."
    )
    LOG_FILE_SERIALIZE = confi.str(
        "LOG_FILE_SERIALIZE", 
        True, 
        description="Serialize log messages in file to JSON format. Facilitates parsing and analysis by log management tools."
    )
    LOG_FILE_LEVEL = confi.str(
        "LOG_FILE_LEVEL", 
        "INFO", 
        description="The log level to show in file. Can be set differently from console logging for more detailed file logs."
    )

    STATISTICS_ENABLED = confi.bool(
        "STATISTICS_ENABLED",
        False,
        description="Enable collection of statistics about OPAL clients. Useful for monitoring and optimization but may cause a small performance hit."
    )
    STATISTICS_ADD_CLIENT_CHANNEL = confi.str(
        "STATISTICS_ADD_CLIENT_CHANNEL",
        "__opal_stats_add",
        description="The topic to update about new OPAL clients connection. Used for real-time monitoring of client connections."
    )
    STATISTICS_REMOVE_CLIENT_CHANNEL = confi.str(
        "STATISTICS_REMOVE_CLIENT_CHANNEL",
        "__opal_stats_rm",
        description="The topic to update about OPAL clients disconnection. Helps track client lifecycle and potential issues."
    )

    # Fetching Providers
    FETCH_PROVIDER_MODULES = confi.list(
        "FETCH_PROVIDER_MODULES", 
        ["opal_common.fetcher.providers"], 
        description="Modules to load fetch providers from. Extend this list to add custom data fetching capabilities for policy and data updates."
    )

    # Fetching engine
    FETCHING_WORKER_COUNT = confi.int(
        "FETCHING_WORKER_COUNT", 
        6, 
        description="Number of worker tasks for handling fetch events concurrently. Adjust based on available resources and expected load."
    )
    FETCHING_CALLBACK_TIMEOUT = confi.int(
        "FETCHING_CALLBACK_TIMEOUT", 
        10, 
        description="Timeout in seconds for fetch task callbacks. Prevents hanging on slow or unresponsive data sources."
    )
    FETCHING_ENQUEUE_TIMEOUT = confi.int(
        "FETCHING_ENQUEUE_TIMEOUT", 
        10, 
        description="Timeout in seconds for enqueueing new fetch tasks. Helps manage backpressure in high-load scenarios."
    )

    GIT_SSH_KEY_FILE = confi.str(
        "GIT_SSH_KEY_FILE", 
        str(Path.home() / ".ssh/opal_repo_ssh_key"), 
        description="Path to SSH key file for Git operations. Used for authenticating with private policy repositories."
    )

    # Trust self signed certificates (Advanced Usage - only affects OPAL client) -----------------------------
    # DO NOT change these defaults unless you absolutely know what you are doing!
    # By default, OPAL client only trusts SSL certificates that are signed by a public recognized CA (certificate authority).
    # However, sometimes (mostly in on-prem setups or in dev environments) users setup their own self-signed certificates.
    # We allow OPAL client to trust these certificates, by changing the following config vars.
    CLIENT_SELF_SIGNED_CERTIFICATES_ALLOWED = confi.bool(
        "CLIENT_SELF_SIGNED_CERTIFICATES_ALLOWED",
        False,
        description="Whether OPAL Client will trust HTTPS connections protected by self-signed certificates. CAUTION: Do not enable in production environments as it reduces security."
    )
    CLIENT_SSL_CONTEXT_TRUSTED_CA_FILE = confi.str(
        "CLIENT_SSL_CONTEXT_TRUSTED_CA_FILE",
        None,
        description="Path to a custom CA public certificate file (.crt or .pem) for OPAL Client to trust. Use for organizational CAs in secure environments. NOT recommended for production use."
    )

    # security
    AUTH_PUBLIC_KEY_FORMAT = confi.enum(
        "AUTH_PUBLIC_KEY_FORMAT", 
        EncryptionKeyFormat, 
        EncryptionKeyFormat.ssh, 
        description="Format of the public key used for authentication. Supports SSH and PEM formats for flexibility in key management."
    )
    AUTH_PUBLIC_KEY = confi.delay(
        lambda AUTH_PUBLIC_KEY_FORMAT=None: confi.public_key(
            "AUTH_PUBLIC_KEY", 
            default=None, 
            key_format=AUTH_PUBLIC_KEY_FORMAT,
            description="The public key used for authentication and JWT token verification. Critical for securing communication between OPAL components."
        )
    )
    AUTH_JWT_ALGORITHM = confi.enum(
        "AUTH_JWT_ALGORITHM",
        JWTAlgorithm,
        getattr(JWTAlgorithm, "RS256"),
        description="JWT algorithm for token signing and verification. RS256 is recommended for production use. See: https://pyjwt.readthedocs.io/en/stable/algorithms.html"
    )
    AUTH_JWT_AUDIENCE = confi.str(
        "AUTH_JWT_AUDIENCE", 
        "https://api.opal.ac/v1/", 
        description="Audience claim for JWT tokens. Should match the intended recipient of the token, typically the OPAL API endpoint."
    )
    AUTH_JWT_ISSUER = confi.str(
        "AUTH_JWT_ISSUER", 
        f"https://opal.ac/", 
        description="Issuer claim for JWT tokens. Identifies the token issuer, usually set to your OPAL server's domain."
    )
    POLICY_REPO_POLICY_EXTENSIONS = confi.list(
        "POLICY_REPO_POLICY_EXTENSIONS",
        [".rego"],
        description="List of file extensions to recognize as policy modules. Extend this list if using custom policy file types beyond Rego."
    )

    ENABLE_METRICS = confi.bool(
        "ENABLE_METRICS", 
        False, 
        description="Enable metrics collection for monitoring OPAL performance and behavior. Useful for operational insights and troubleshooting."
    )

    # optional APM tracing with datadog
    ENABLE_DATADOG_APM = confi.bool(
        "ENABLE_DATADOG_APM",
        False,
        description="Enable tracing with Datadog APM for advanced performance monitoring and distributed tracing capabilities."
    )
    HTTP_FETCHER_PROVIDER_CLIENT = confi.str(
        "HTTP_FETCHER_PROVIDER_CLIENT",
        "aiohttp",
        description="The HTTP client library to use for fetching data. Options: 'aiohttp' or 'httpx'. Affects performance and features of HTTP-based data fetching."
    )


opal_common_config = OpalCommonConfig(prefix="OPAL_")