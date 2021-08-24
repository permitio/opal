import os

from opal_common.confi import Confi
from opal_common.schemas.data import ServerDataSourceConfig
from opal_common.authentication.types import EncryptionKeyFormat, JWTAlgorithm

confi = Confi(prefix="OPAL_")


class OpalServerConfig(Confi):
    # ws server
    OPAL_WS_LOCAL_URL = confi.str("WS_LOCAL_URL", "ws://localhost:7002/ws")
    OPAL_WS_TOKEN = confi.str("WS_TOKEN", "THIS_IS_A_DEV_SECRET")
    BROADCAST_URI = confi.str("BROADCAST_URI", None)

    # server security
    AUTH_PRIVATE_KEY_FORMAT = confi.enum("AUTH_PRIVATE_KEY_FORMAT", EncryptionKeyFormat, EncryptionKeyFormat.pem)
    AUTH_PRIVATE_KEY_PASSPHRASE = confi.str("AUTH_PRIVATE_KEY_PASSPHRASE", None)

    AUTH_PRIVATE_KEY = confi.delay(
        lambda AUTH_PRIVATE_KEY_FORMAT=None, AUTH_PRIVATE_KEY_PASSPHRASE="":
            confi.private_key(
                "AUTH_PRIVATE_KEY",
                default=None,
                key_format=AUTH_PRIVATE_KEY_FORMAT,
                passphrase=AUTH_PRIVATE_KEY_PASSPHRASE
            )
    )

    AUTH_PUBLIC_KEY_FORMAT = confi.enum("AUTH_PUBLIC_KEY_FORMAT", EncryptionKeyFormat, EncryptionKeyFormat.ssh)
    AUTH_PUBLIC_KEY = confi.delay(
        lambda AUTH_PUBLIC_KEY_FORMAT=None:
            confi.public_key(
                "AUTH_PUBLIC_KEY",
                default=None,
                key_format=AUTH_PUBLIC_KEY_FORMAT
            )
    )
    AUTH_JWT_ALGORITHM = confi.enum(
        "AUTH_JWT_ALGORITHM",
        JWTAlgorithm,
        getattr(JWTAlgorithm, "RS256"),
        description="jwt algorithm, possible values: see: https://pyjwt.readthedocs.io/en/stable/algorithms.html"
    )
    AUTH_JWT_AUDIENCE = confi.str("AUTH_JWT_AUDIENCE", "https://api.authorizon.com/v1/")
    AUTH_JWT_ISSUER = confi.str("AUTH_JWT_ISSUER", f"https://authorizon.com/")

    AUTH_JWKS_URL = confi.str("AUTH_JWKS_URL", "/.well-known/jwks.json")
    AUTH_JWKS_STATIC_DIR = confi.str("AUTH_JWKS_STATIC_DIR", os.path.join(os.getcwd(), "jwks_dir"))

    AUTH_MASTER_TOKEN = confi.str("AUTH_MASTER_TOKEN", None)

    # repo watcher
    POLICY_REPO_URL = confi.str("POLICY_REPO_URL", None)
    POLICY_REPO_CLONE_PATH = confi.str("POLICY_REPO_CLONE_PATH", os.path.join(os.getcwd(), "regoclone"))
    POLICY_REPO_MAIN_BRANCH = confi.str("POLICY_REPO_MAIN_BRANCH", "master")
    POLICY_REPO_MAIN_REMOTE = confi.str("POLICY_REPO_MAIN_REMOTE", "origin")
    POLICY_REPO_SSH_KEY = confi.str("POLICY_REPO_SSH_KEY", None)
    POLICY_REPO_MANIFEST_PATH = confi.str("POLICY_REPO_MANIFEST_PATH", ".manifest")
    POLICY_REPO_CLONE_TIMEOUT = confi.int("POLICY_REPO_CLONE_TIMEOUT", 0) # if 0, waits forever until successful clone
    LEADER_LOCK_FILE_PATH = confi.str("LEADER_LOCK_FILE_PATH", "/tmp/opal_server_leader.lock")

    REPO_WATCHER_ENABLED = confi.bool("REPO_WATCHER_ENABLED", True)

    # publisher
    PUBLISHER_ENABLED = confi.bool("PUBLISHER_ENABLED", True)

    # Data updates
    ALL_DATA_TOPIC = confi.str("ALL_DATA_TOPIC", "policy_data", description="Top level topic for data")
    ALL_DATA_ROUTE = confi.str("ALL_DATA_ROUTE", "/policy-data")
    ALL_DATA_URL = confi.str("ALL_DATA_URL", confi.delay(
        "http://localhost:7002{ALL_DATA_ROUTE}"), description="URL for all data config [If you choose to have it all at one place]")
    DATA_CONFIG_ROUTE = confi.str("DATA_CONFIG_ROUTE", "/data/config",
                                  description="URL to fetch the full basic configuration of data")
    DATA_CALLBACK_DEFAULT_ROUTE = confi.str("DATA_CALLBACK_DEFAULT_ROUTE", "/data/callback_report",
        description="Exists as a sane default in case the user did not set OPAL_DEFAULT_UPDATE_CALLBACKS")

    DATA_CONFIG_SOURCES = confi.model(
        "DATA_CONFIG_SOURCES",
        ServerDataSourceConfig,
        confi.delay(lambda ALL_DATA_URL="", ALL_DATA_TOPIC="": {
            "config": {
                "entries": [
                    {"url": ALL_DATA_URL, "topics": [ALL_DATA_TOPIC]}
                ]
            }
        }),
        description="Configuration of data sources by topics"
    )

    DATA_UPDATE_TRIGGER_ROUTE = confi.str("DATA_CONFIG_ROUTE", "/data/update",
                                          description="URL to trigger data update events")

    # github webhook
    POLICY_REPO_WEBHOOK_SECRET = confi.str("POLICY_REPO_WEBHOOK_SECRET", None)
    POLICY_REPO_WEBHOOK_TOPIC = "webhook"

    POLICY_REPO_POLLING_INTERVAL = confi.int("POLICY_REPO_POLLING_INTERVAL", 0)

    ALLOWED_ORIGINS = confi.list("ALLOWED_ORIGINS", ["*"])
    OPA_FILE_EXTENSIONS = ('.rego', '.json')

    NO_RPC_LOGS = confi.bool("NO_RPC_LOGS", True)

    # client-api server
    SERVER_WORKER_COUNT = confi.int("SERVER_WORKER_COUNT", None,
                                    description="(if run via CLI) Worker count for the server [Default calculated to CPU-cores]")

    SERVER_HOST = confi.str("SERVER_HOST", "127.0.0.1",
                            description="(if run via CLI)  Address for the server to bind")

    SERVER_PORT = confi.int("SERVER_PORT", 7002,
                            description="(if run via CLI)  Port for the server to bind")


opal_server_config = OpalServerConfig(prefix="OPAL_")
