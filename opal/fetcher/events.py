import typing
from pydantic import BaseModel


class FetchEvent(BaseModel):
    name:str = ""
    fetcher:str
    url: str
    fetcher_config: typing.Any = None

