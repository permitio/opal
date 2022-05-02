from pydantic import BaseModel


class Repository(BaseModel):
    git_url: str
    ssh_url: str
    clone_url: str


class PushWebHook(BaseModel):
    repository: Repository
    before: str
    after: str
