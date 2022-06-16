from typing import List, Optional, Union

try:
    from typing import Literal
except ImportError:
    # Py<3.8
    from typing_extensions import Literal

from opal_common.schemas.policy import BaseSchema
from pydantic import Field


class NoAuthData(BaseSchema):
    auth_type: Literal["none"] = "none"


class SSHAuthData(BaseSchema):
    auth_type: Literal["ssh"] = "ssh"
    username: str = Field(..., description="SSH username")
    public_key: Optional[str] = Field(None, description="SSH public key")
    private_key: str = Field(..., description="SSH private key")


class GitHubTokenAuthData(BaseSchema):
    auth_type: Literal["github_token"] = "github_token"
    token: str = Field(..., description="Github Personal Access Token (PAI)")


class UserPassAuthData(BaseSchema):
    auth_type: Literal["userpass"] = "userpass"
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class BasePolicyScopeSource(BaseSchema):
    source_type: str
    url: str
    auth: Union[NoAuthData, SSHAuthData, GitHubTokenAuthData, UserPassAuthData] = Field(
        ..., discriminator="auth_type"
    )
    directories: List[str] = Field(["."], description="Directories to include")
    extensions: List[str] = Field(
        [".rego", ".json"], description="File extensions to use"
    )
    manifest: str = Field(".manifest", description="path to manifest file")
    poll_updates: bool = Field(
        False, description="Whether OPAL should check for updates periodically"
    )


class GitPolicyScopeSource(BasePolicyScopeSource):
    branch: str = Field("main", description="Git branch to track")
