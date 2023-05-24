from pathlib import Path

from opal_common.authentication.casting import cast_public_key
from opal_common.authentication.types import (
    EncryptionKeyFormat,
    JWTAlgorithm,
    PublicKey,
)
from pydantic import BaseSettings, Field, validator

_LOG_FORMAT_WITHOUT_PID = "<green>{time}</green> | <blue>{name: <40}</blue>|<level>{level:^6} | {message}</level>\n{exception}"
_LOG_FORMAT_WITH_PID = "<green>{time}</green> | {process} | <blue>{name: <40}</blue>|<level>{level:^6} | {message}</level>\n{exception}"


class OpalSettings(BaseSettings):
    class Config:
        env_prefix = "OPAL_"


# Process name to show in logs - Not confi-controlable on purpose
PROCESS_NAME = ""


class CommonStatisticsConfig(OpalSettings):
    STATISTICS_ENABLED: bool = Field(
        False,
        description="Set if OPAL server will collect statistics about OPAL clients may cause a small performance hit",
    )
    STATISTICS_ADD_CLIENT_CHANNEL: str = Field(
        "__opal_stats_add",
        description="The topic to update about new OPAL clients connection",
    )
    STATISTICS_REMOVE_CLIENT_CHANNEL: str = Field(
        "__opal_stats_rm",
        description="The topic to update about OPAL clients disconnection",
    )


class OpalCommonConfig(OpalSettings):
    ALLOWED_ORIGINS: list = Field(["*"], description="List of allowed origins for CORS")

    class LoggingConfig(OpalSettings):
        LOG_FORMAT_INCLUDE_PID: bool = False
        LOG_FORMAT: str = Field(
            None,
            description="The format of the log messages",
        )

        @validator("LOG_FORMAT", pre=True)
        def log_format(cls, v, values):
            if v is None:
                return (
                    _LOG_FORMAT_WITH_PID
                    if values["LOG_FORMAT_INCLUDE_PID"]
                    else _LOG_FORMAT_WITHOUT_PID
                )
            return v

        LOG_TRACEBACK: bool = Field(
            True, description="Include traceback in log messages"
        )
        LOG_DIAGNOSE: bool = Field(
            True, description="Include diagnosis in log messages"
        )
        LOG_COLORIZE: bool = Field(True, description="Colorize log messages")
        LOG_SERIALIZE: bool = Field(False, description="Serialize log messages")
        LOG_SHOW_CODE_LINE: bool = Field(
            True, description="Show code line in log messages"
        )
        #  - log level
        LOG_LEVEL: str = Field("INFO", description="The log level to show")
        #  - Which modules should be logged
        LOG_MODULE_EXCLUDE_LIST: list = Field(
            [
                "uvicorn",
                # NOTE: the env var LOG_MODULE_EXCLUDE_OPA affects this list
            ],
            description="List of modules to exclude from logging",
        )
        LOG_MODULE_INCLUDE_LIST: list = Field(
            ["uvicorn.protocols.http"],
            description="List of modules to include in logging",
        )
        LOG_PATCH_UVICORN_LOGS: bool = Field(
            True,
            description="Should we takeover UVICORN's logs so they appear in the main logger",
        )
        # - Log to file as well ( @see https://github.com/Delgan/loguru#easier-file-logging-with-rotation--retention--compression)
        LOG_TO_FILE: bool = Field(False, description="Should we log to a file")
        LOG_FILE_PATH: str = Field(
            f"opal_{PROCESS_NAME}{{time}}.log",
            description="path to save log file",
        )
        LOG_FILE_ROTATION: str = Field("250 MB", description="Log file rotation size")
        LOG_FILE_RETENTION: str = Field(
            "10 days", description="Log file retention time"
        )
        LOG_FILE_COMPRESSION: str = Field(
            None, description="Log file compression format"
        )
        LOG_FILE_SERIALIZE: str = Field(
            True, description="Serialize log messages in file"
        )
        LOG_FILE_LEVEL: str = Field("INFO", description="The log level to show in file")

    logging: LoggingConfig = LoggingConfig()

    class FetchingConfig(OpalSettings):
        # Fetching Providers
        # - where to load providers from
        FETCH_PROVIDER_MODULES: list = ["opal_common.fetcher.providers"]

        # Fetching engine
        # Max number of worker tasks handling fetch events concurrently
        FETCHING_WORKER_COUNT: int = 5
        # Time in seconds to wait on the queued fetch task.
        FETCHING_CALLBACK_TIMEOUT: int = 10
        # Time in seconds to wait for queuing a new task (if the queue is full)
        FETCHING_ENQUEUE_TIMEOUT: int = 10

    fetchers: FetchingConfig = FetchingConfig()

    GIT_SSH_KEY_FILE: str = str(Path.home() / ".ssh/opal_repo_ssh_key")

    # TODO: Could that be only in client?
    # Trust self signed certificates (Advanced Usage - only affects OPAL client) -----------------------------
    # DO NOT change these defaults unless you absolutely know what you are doing!
    # By default, OPAL client only trusts SSL certificates that are signed by a public recognized CA (certificate authority).
    # However, sometimes (mostly in on-prem setups or in dev environments) users setup their own self-signed certificates.
    # We allow OPAL client to trust these certificates, by changing the following config vars.
    CLIENT_SELF_SIGNED_CERTIFICATES_ALLOWED: bool = Field(
        False,
        description="Whether or not OPAL Client will trust HTTPs connections protected by self signed certificates. DO NOT USE THIS IN PRODUCTION!",
    )
    CLIENT_SSL_CONTEXT_TRUSTED_CA_FILE: str = Field(
        None,
        description="A path to your own CA public certificate file (usually a .crt or a .pem file). Certificates signed by this issuer will be trusted by OPAL Client. DO NOT USE THIS IN PRODUCTION!",
    )

    class SecurityConfig(OpalSettings):
        AUTH_PUBLIC_KEY_FORMAT: EncryptionKeyFormat = EncryptionKeyFormat.ssh
        AUTH_PUBLIC_KEY: PublicKey = None

        @validator("AUTH_PUBLIC_KEY", pre=True)
        def auth_publick_key(cls, v, values):
            if v is not None:
                return cast_public_key(v, values["AUTH_PUBLIC_KEY_FORMAT"])

        AUTH_JWT_ALGORITHM: JWTAlgorithm = Field(
            getattr(JWTAlgorithm, "RS256"),
            description="jwt algorithm, possible values: see: https://pyjwt.readthedocs.io/en/stable/algorithms.html",
        )
        AUTH_JWT_AUDIENCE: str = "https://api.opal.ac/v1/"
        AUTH_JWT_ISSUER: str = f"https://opal.ac/"

    security: SecurityConfig = SecurityConfig()

    POLICY_REPO_POLICY_EXTENSIONS: list = Field(
        [".rego"],
        description="List of extensions to serve as policy modules",
    )


opal_common_config = OpalCommonConfig()
