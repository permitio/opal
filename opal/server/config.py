from opal.common.confi import Confi


confi = Confi()

# ws server (TODO: merge with opal client config)
OPAL_WS_LOCAL_URL = confi.str("OPAL_WS_LOCAL_URL", "ws://localhost:7002/ws")
OPAL_WS_TOKEN = confi.str("OPAL_WS_TOKEN", "THIS_IS_A_DEV_SECRET")
BROADCAST_URI = confi.str("BROADCAST_URI", "postgres://localhost/acalladb")

# repo watcher
POLICY_REPO_URL = confi.str("POLICY_REPO_URL", None)
POLICY_REPO_CLONE_PATH = confi.str("POLICY_REPO_CLONE_PATH", "regoclone")
POLICY_REPO_MAIN_BRANCH = confi.str("POLICY_REPO_MAIN_BRANCH", "master")
POLICY_REPO_MAIN_REMOTE = confi.str("POLICY_REPO_MAIN_REMOTE", "origin")

# github webhook
POLICY_REPO_WEBHOOK_SECRET = confi.str("POLICY_REPO_WEBHOOK_SECRET", None)

POLICY_REPO_POLLING_INTERVAL = confi.int("POLICY_REPO_POLLING_INTERVAL", 0)


ALLOWED_ORIGINS = confi.list("ALLOWED_ORIGINS", ["*"])
OPA_FILE_EXTENSIONS = ('.rego', '.json')

NO_RPC_LOGS = confi.bool("NO_RPC_LOGS", True)