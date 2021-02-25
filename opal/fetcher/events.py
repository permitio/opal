import typing
from pydantic import BaseModel


class FetcherConfig(BaseModel):
    pass

class FetchEvent(BaseModel):
    """
    Event used to descrive an queue fetching tasks
    """
    # optional name of the specific event
    name:str = ""
    # A string identifying the fetcher class to use (as registered in the fetcher arsenal)
    fetcher:str
    # The url the event targets for fetching
    url: str
    #  Specific fetcher configuration (overridden by deriving event classes)
    config: FetcherConfig = None

