from pydantic import Field
from typing import List

from opal_common.schemas.policy import BaseSchema


class PolicySource(BaseSchema):
    source_type: str
    url: str
    directories: List[str] = Field(['.'], description='Directories to include')
    manifest: str = Field('.manifest', description='path to manifest file')

