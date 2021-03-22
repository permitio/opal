from opal.common.confi import Confi
from opal.common.schemas.data import DataSourceConfig
from opal.common.authentication.keys import EncryptionKeyFormat, JWTAlgorithm

confi = Confi()
# ws server (TODO: merge with opal client config)
OPAL_WS_LOCAL_URL = confi.str("OPAL_WS_LOCAL_URL", "ws://localhost:7002/ws")
OPAL_WS_TOKEN = confi.str("OPAL_WS_TOKEN", "THIS_IS_A_DEV_SECRET")
BROADCAST_URI = confi.str("BROADCAST_URI", "postgres://localhost/acalladb")

# server security
AUTH_PRIVATE_KEY_FORMAT = confi.enum("AUTH_PRIVATE_KEY_FORMAT", EncryptionKeyFormat, EncryptionKeyFormat.pem)
AUTH_PRIVATE_KEY_PASSPHRASE = confi.str("AUTH_PRIVATE_KEY_PASSPHRASE", "")
AUTH_PRIVATE_KEY = confi.str("AUTH_PRIVATE_KEY", None)

AUTH_PUBLIC_KEY_FORMAT = confi.enum("AUTH_PUBLIC_KEY_FORMAT", EncryptionKeyFormat, EncryptionKeyFormat.ssh)
AUTH_PUBLIC_KEY = confi.str("AUTH_PUBLIC_KEY", None)
AUTH_JWT_ALGORITHM = confi.enum(
    "AUTH_JWT_ALGORITHM",
    JWTAlgorithm,
    getattr(JWTAlgorithm, "RS256"),
    description="jwt algorithm, possible values: see: https://pyjwt.readthedocs.io/en/stable/algorithms.html"
)
AUTH_MASTER_TOKEN = confi.str("AUTH_MASTER_TOKEN", None)

# repo watcher
POLICY_REPO_URL = confi.str("POLICY_REPO_URL", None)
POLICY_REPO_CLONE_PATH = confi.str("POLICY_REPO_CLONE_PATH", "~/regoclone")
POLICY_REPO_MAIN_BRANCH = confi.str("POLICY_REPO_MAIN_BRANCH", "master")
POLICY_REPO_MAIN_REMOTE = confi.str("POLICY_REPO_MAIN_REMOTE", "origin")
POLICY_REPO_SSH_KEY = confi.str("POLICY_REPO_SSH_KEY", None)
LEADER_LOCK_FILE_PATH = confi.str("LEADER_LOCK_FILE_PATH", "/tmp/opal_server_leader.lock")

# Data updates
ALL_DATA_TOPIC = confi.str("ALL_DATA_TOPIC", "policy_data", description="Top level topic for data")
ALL_DATA_URL = confi.str("ALL_DATA_URL", "http://localhost:7002/policy-data", description="URL for all data config [If you choose to have it all at one place]")
DATA_CONFIG_ROUTE = confi.str("DATA_CONFIG_ROUTE", "/data/config", description="URL to fetch the full basic configuration of data")
DATA_CONFIG_SOURCES = confi.model(
    "DATA_CONFIG_SOURCES",
    DataSourceConfig,
    {
        "entries":[
            {"url": ALL_DATA_URL, "topics":[ALL_DATA_TOPIC]}
        ]
    },
    description="Configuration of data sources by topics"
)

DATA_UPDATE_TRIGGER_ROUTE = confi.str("DATA_CONFIG_ROUTE", "/data/update", description="URL to trigger data update events")


# github webhook
POLICY_REPO_WEBHOOK_SECRET = confi.str("POLICY_REPO_WEBHOOK_SECRET", None)

POLICY_REPO_POLLING_INTERVAL = confi.int("POLICY_REPO_POLLING_INTERVAL", 0)


ALLOWED_ORIGINS = confi.list("ALLOWED_ORIGINS", ["*"])
OPA_FILE_EXTENSIONS = ('.rego', '.json')

NO_RPC_LOGS = confi.bool("NO_RPC_LOGS", True)