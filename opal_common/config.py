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

    # Trust self signed certificates (Advanced Usage - only affects OPAL client) -----------------------------
    # DO NOT change these defaults unless you absolutely know what you are doing!
    # By default, OPAL client only trusts SSL certificates that are signed by a public recognized CA (certificate authority).
    # However, sometimes (mostly in on-prem setups or in dev environments) users setup their own self-signed certificates.
    # We allow OPAL client to trust these certificates, by changing the following config vars.
    CLIENT_SELF_SIGNED_CERTIFICATES_ALLOWED=confi.bool(
        "CLIENT_SELF_SIGNED_CERTIFICATES_ALLOWED", False,
        description="Whether or not OPAL Client will trust HTTPs connections protected by self signed certificates. DO NOT USE THIS IN PRODUCTION!")
    CLIENT_SSL_CONTEXT_TRUSTED_CA_FILE=confi.str(
        "CLIENT_SSL_CONTEXT_TRUSTED_CA_FILE", None,
        description="A path to your own CA public certificate file (usually a .crt or a .pem file). Certifcates signed by this issuer will be trusted by OPAL Client. DO NOT USE THIS IN PRODUCTION!")


opal_common_config = OpalCommonConfig(prefix="OPAL_")


