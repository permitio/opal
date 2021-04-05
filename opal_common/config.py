from pathlib import Path
from sys import prefix
from .confi import Confi, confi

class OpalCommonConfig(Confi):
    ALLOWED_ORIGINS = confi.list("ALLOWED_ORIGINS", ["*"])
    # Process name to show in logs - Not confi-controlable on purpose 
    PROCESS_NAME = ""
    # Logging
    # - Log formatting
    LOG_TRACEBACK = confi.bool("LOG_TRACEBACK", True)
    LOG_DIAGNOSE = confi.bool("LOG_DIAGNOSE", True)
    LOG_COLORIZE = confi.bool("LOG_COLORIZE", True)
    LOG_SHOW_CODE_LINE = confi.bool("LOG_SHOW_CODE_LINE", True)
    #  - log level
    LOG_LEVEL = confi.str("LOG_LEVEL", "INFO")
    #  - Which modules should be logged
    LOG_MODULE_EXCLUDE_LIST = confi.list("LOG_MODULE_EXCLUDE_LIST", [
        "fastapi_websocket_rpc",
        "fastapi_websocket_pubsub",
        "uvicorn",
        # NOTE: the env var LOG_MODULE_EXCLUDE_OPA affects this list
    ])
    LOG_MODULE_INCLUDE_LIST = confi.list("LOG_MODULE_INCLUDE_LIST", ["uvicorn.protocols.http"])
    LOG_PATCH_UVICORN_LOGS = confi.bool("LOG_PATCH_UVICORN_LOGS", True,
                                        description="Should we takeover UVICORN's logs so they appear in the main logger")
    # - Log to file as well ( @see https://github.com/Delgan/loguru#easier-file-logging-with-rotation--retention--compression)
    LOG_TO_FILE = confi.bool("LOG_TO_FILE", False, description="Should we log to a file")
    LOG_FILE_PATH = confi.str("LOG_FILE_PATH", f"opal_{PROCESS_NAME}{{time}}.log", description="path to save log file")
    LOG_FILE_ROTATION = confi.str("LOG_FILE_ROTATION", "250 MB")
    LOG_FILE_RETENTION = confi.str("LOG_FILE_RETENTION", "10 days")
    LOG_FILE_COMPRESSION = confi.str("LOG_FILE_COMPRESSION", None)
    LOG_FILE_SERIALIZE = confi.str("LOG_FILE_SERIALIZE", True)
    LOG_FILE_LEVEL = confi.str("LOG_FILE_LEVEL", "INFO")

    # Fetching Providers
    # - where to load providers from
    FETCH_PROVIDER_MODULES = confi.list("FETCH_PROVIDER_MODULES", ["opal_common.fetcher.providers"])

    GIT_SSH_KEY_FILE = confi.str("GIT_SSH_KEY_FILE", str(Path.home() / ".ssh/opal_repo_ssh_key"))



opal_common_config = OpalCommonConfig(prefix="OPAL_")


