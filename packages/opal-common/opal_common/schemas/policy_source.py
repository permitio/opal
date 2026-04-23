from typing import List, Optional, Union

try:
    from typing import Literal
except ImportError:
    # Py<3.8
    from typing_extensions import Literal

from opal_common.schemas.policy import BaseSchema
from pydantic import Field, root_validator


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
    bundle_ignore: Optional[List[str]] = Field(
        None, description="glob paths to omit from bundle"
    )
    manifest: str = Field(".manifest", description="path to manifest file")
    poll_updates: bool = Field(
        False, description="Whether OPAL should check for updates periodically"
    )


class GitPolicyScopeSource(BasePolicyScopeSource):
    branch: Optional[str] = Field(None, description="Git branch to track")
    tag: Optional[str] = Field(None, description="Git tag to track")

    @root_validator
    def validate_branch_or_tag(cls, values):
        branch = values.get("branch") or None
        tag = values.get("tag") or None
        values["branch"] = branch
        values["tag"] = tag
        if branch is None and tag is None:
            raise ValueError("Must provide either 'branch' or 'tag'")
        if branch is not None and tag is not None:
            raise ValueError("Must provide either 'branch' or 'tag', not both")
        return values
