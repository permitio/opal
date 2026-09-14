import re
from enum import Enum
from typing import Any, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

HOST_ADDR_PATTERN = re.compile(
    r"^(?P<addr>(?:\d{1,3}\.){3}\d{1,3}|)(?::(?P<port>\d+))?$"
)


def _cli_alias(field_name: str) -> str:
    """Converts a field named tls_private_key_file to --tls-private-key-file
    (to be used by the opa/cedar cli).

    Was a ``Config.alias_generator`` classmethod under pydantic v1; v2
    takes the generator as a plain callable on ``model_config``.
    """
    return "--{}".format(field_name.replace("_", "-"))


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
        "0.0.0.0:8181",
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
    tls_cert_refresh_period: Optional[str] = Field(
        None,
        description="how often OPA should check the TLS certificate and private key file for changes",
    )
    log_level: LogLevel = Field(LogLevel.info, description="log level for opa logs")
    files: Optional[List[str]] = Field(
        None,
        description="list of built-in rego policies and data.json files that must be loaded into OPA on startup. e.g: system.authz policy when using --authorization=basic, see: https://www.openpolicyagent.org/docs/latest/security/#authentication-and-authorization",
    )
    v0_compatible: bool = Field(
        False,
        description="set to true to enable the OPA v0 compatibility mode (default false)",
    )

    model_config = ConfigDict(
        use_enum_values=True,
        populate_by_name=True,
        alias_generator=_cli_alias,
    )

    def get_cli_options_dict(self):
        """Returns a dict that can be passed to the OPA cli."""
        return self.model_dump(
            exclude_none=True, by_alias=True, exclude={"files", "v0_compatible"}
        )


class CedarServerOptions(BaseModel):
    """Options to configure the Cedar agent (apply when choosing to run Cedar
    inline)."""

    addr: str = Field(
        "0.0.0.0:8180",
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

    model_config = ConfigDict(
        use_enum_values=True,
        populate_by_name=True,
        alias_generator=_cli_alias,
    )

    @field_validator("authentication")
    @classmethod
    def validate_authentication(cls, v: AuthenticationScheme):
        if v not in [AuthenticationScheme.off, AuthenticationScheme.token]:
            raise ValueError("Invalid AuthenticationScheme for Cedar.")
        return v

    @field_validator("authentication_token")
    @classmethod
    def validate_authentication_token(cls, v: Optional[str], info: ValidationInfo):
        if info.data.get("authentication") == AuthenticationScheme.token and v is None:
            raise ValueError(
                "A token must be specified for AuthenticationScheme.token."
            )
        return v

    def get_args(self) -> Iterable[str]:
        if (
            self.authentication == AuthenticationScheme.token
            and self.authentication_token is not None
        ):
            yield "-a"
            yield self.authentication_token

        match = HOST_ADDR_PATTERN.match(self.addr)
        if not match:
            raise ValueError(
                f"Invalid addr format: {self.addr}. Expected [ip]:<port>, e.g. '0.0.0.0:8180', ':8180'"
            )

        yield "--addr"
        yield match.group("addr") or "0.0.0.0"
        yield "--port"
        yield match.group("port") or "8180"

        # TODO: files
