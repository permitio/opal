import typing
from pydantic import BaseModel


class FetcherConfig(BaseModel):
    pass

class FetchEvent(BaseModel):
    name:str = ""
    fetcher:str
    url: str
    #  Specific fetcher configuration 
    fetcher_config: FetcherConfig = None

