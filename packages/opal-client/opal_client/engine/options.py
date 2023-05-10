from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, validator


class LogLevel(str, Enum):
    info = "info"
    debug = "debug"
    error = "error"


class AuthenticationScheme(str, Enum):
    off = "off"
    token = "token"
    tls = "tls"


class AuthorizationScheme(str, Enum):
    off = "off"
    basic = "basic"


class OpaServerOptions(BaseModel):
    """Options to configure OPA server (apply when choosing to run OPA inline).

    Security options are explained here in detail: https://www.openpolicyagent.org/docs/latest/security/
    these include:
    - addr (use https:// to apply TLS on OPA server)
    - authentication (affects how clients are authenticating to OPA server)
    - authorization (toggles the data.system.authz.allow document as the authz policy applied on each request)
    - tls_ca_cert_file (CA cert for the CA signing on *client* tokens, when authentication=tls is on)
    - tls_cert_file (TLS cert for the OPA server HTTPS)
    - tls_private_key_file (TLS private key for the OPA server HTTPS)
    """

    addr: str = Field(
        ":8181",
        description="listening address of the opa server (e.g., [ip]:<port> for TCP)",
    )
    authentication: AuthenticationScheme = Field(
        AuthenticationScheme.off, description="opa authentication scheme (default off)"
    )
    authorization: AuthorizationScheme = Field(
        AuthorizationScheme.off, description="opa authorization scheme (default off)"
    )
    config_file: Optional[str] = Field(
        None,
        description="path of opa configuration file (format defined here: https://www.openpolicyagent.org/docs/latest/configuration/)",
    )
    tls_ca_cert_file: Optional[str] = Field(
        None, description="path of TLS CA cert file"
    )
    tls_cert_file: Optional[str] = Field(
        None, description="path of TLS certificate file"
    )
    tls_private_key_file: Optional[str] = Field(
        None, description="path of TLS private key file"
    )
    log_level: LogLevel = Field(LogLevel.info, description="log level for opa logs")
    files: Optional[List[str]] = Field(
        None,
        description="list of built-in rego policies and data.json files that must be loaded into OPA on startup. e.g: system.authz policy when using --authorization=basic, see: https://www.openpolicyagent.org/docs/latest/security/#authentication-and-authorization",
    )

    class Config:
        use_enum_values = True
        allow_population_by_field_name = True

        @classmethod
        def alias_generator(cls, string: str) -> str:
            """converts field named tls_private_key_file to --tls-private-key-
            file (to be used by opa cli)"""
            return "--{}".format(string.replace("_", "-"))

    def get_cli_options_dict(self):
        """returns a dict that can be passed to the OPA cli."""
        return self.dict(exclude_none=True, by_alias=True, exclude={"files"})

    def get_opa_startup_files(self) -> str:
        """returns a list of startup policies and data."""
        files = self.files if self.files is not None else []
        return " ".join(files)


class CedarServerOptions(BaseModel):
    """Options to configure the Cedar agent (apply when choosing to run Cedar
    inline)."""

    addr: str = Field(
        ":8181",
        description="listening address of the Cedar agent (e.g., [ip]:<port> for TCP)",
    )
    authentication: AuthenticationScheme = Field(
        AuthenticationScheme.off,
        description="Cedar agent authentication scheme (default off)",
    )
    authentication_token: Optional[str] = Field(
        None,
        description="If authentication is 'token', this specifies the token to use.",
    )
    files: Optional[List[str]] = Field(
        None,
        description="list of built-in policies files that must be loaded on startup.",
    )

    class Config:
        use_enum_values = True
        allow_population_by_field_name = True

        @classmethod
        def alias_generator(cls, string: str) -> str:
            """converts field named tls_private_key_file to --tls-private-key-
            file (to be used by opa cli)"""
            return "--{}".format(string.replace("_", "-"))

    @validator("authentication")
    def validate_authentication(cls, v: AuthenticationScheme):
        if v not in [AuthenticationScheme.off, AuthenticationScheme.token]:
            raise ValueError("Invalid AuthenticationScheme for Cedar.")
        return v

    @validator("authentication_token")
    def validate_authentication_token(cls, v: Optional[str], values: dict[str, Any]):
        if values["authentication"] == AuthenticationScheme.token and v is None:
            raise ValueError(
                "A token must be specified for AuthenticationScheme.token."
            )
        return v

    def get_cmdline(self) -> str:
        result = [
            "cedar-agent",
        ]
        if (
            self.authentication == AuthenticationScheme.token
            and self.authentication_token is not None
        ):
            result += [
                "-a",
                self.authentication_token,
            ]
        addr = self.addr.split(":", 1)
        port = None
        if len(addr) == 1:
            listen_address = addr[0]
        elif len(addr) == 2:
            listen_address, port = addr
        if len(listen_address) == 0:
            listen_address = "0.0.0.0"
        result += [
            "--addr",
            listen_address,
        ]
        if port is not None:
            result += [
                "--port",
                port,
            ]
        # TODO: files
        return " ".join(result)
