from typing import ClassVar, List, Optional, Set, Union

try:
    from typing import Literal
except ImportError:
    # Py<3.8
    from typing_extensions import Literal

from opal_common.logging_utils.redaction import RedactedReprMixin
from opal_common.schemas.policy import BaseSchema
from pydantic import ConfigDict, Field

# The auth models below carry git auth material. ``RedactedReprMixin`` masks it
# in repr/str (log rendering) and ``hide_input_in_errors`` keeps it out of the
# text of a ValidationError raised while validating the model directly. Neither
# changes ``model_dump()`` / ``model_dump_json()``, so the wire format and the
# records persisted in Redis are unaffected.


class NoAuthData(BaseSchema):
    auth_type: Literal["none"] = "none"


class SSHAuthData(RedactedReprMixin, BaseSchema):
    model_config = ConfigDict(hide_input_in_errors=True)
    _redacted_repr_fields: ClassVar[Set[str]] = {"private_key"}

    auth_type: Literal["ssh"] = "ssh"
    username: str = Field(..., description="SSH username")
    public_key: Optional[str] = Field(None, description="SSH public key")
    private_key: str = Field(..., description="SSH private key")


class GitHubTokenAuthData(RedactedReprMixin, BaseSchema):
    model_config = ConfigDict(hide_input_in_errors=True)
    _redacted_repr_fields: ClassVar[Set[str]] = {"token"}

    auth_type: Literal["github_token"] = "github_token"
    token: str = Field(..., description="Github Personal Access Token (PAI)")


class UserPassAuthData(RedactedReprMixin, BaseSchema):
    model_config = ConfigDict(hide_input_in_errors=True)
    _redacted_repr_fields: ClassVar[Set[str]] = {"password"}

    auth_type: Literal["userpass"] = "userpass"
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class BasePolicyScopeSource(RedactedReprMixin, BaseSchema):
    model_config = ConfigDict(hide_input_in_errors=True)
    # ``url`` can embed ``user:token@`` or ``?token=``; redact_url strips those
    # while keeping the host and path visible.
    _redacted_url_fields: ClassVar[Set[str]] = {"url"}

    source_type: str
    url: str
    auth: Union[NoAuthData, SSHAuthData, GitHubTokenAuthData, UserPassAuthData] = Field(
        ..., discriminator="auth_type"
    )
    directories: List[str] = Field(["."], description="Directories to include")
    extensions: List[str] = Field(
        [".rego", ".json"], description="File extensions to use"
    )
    bundle_ignore: Optional[List[str]] = Field(
        None, description="glob paths to omit from bundle"
    )
    manifest: str = Field(".manifest", description="path to manifest file")
    poll_updates: bool = Field(
        False, description="Whether OPAL should check for updates periodically"
    )


class GitPolicyScopeSource(BasePolicyScopeSource):
    branch: str = Field("main", description="Git branch to track")
