from pydantic import Field
from typing import Optional
import shutil

OPA_EXECUTABLE_PATH: Optional[str] = Field(
    default=None,
    env="OPAL_OPA_EXECUTABLE_PATH",
    description="Custom filesystem path to the OPA binary executable",
)

def get_opa_executable(custom_path: Optional[str] = None) -> str:
    return custom_path or OPA_EXECUTABLE_PATH or shutil.which("opa") or "opa"
