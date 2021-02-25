from pydantic import BaseModel


class FetcherConfig(BaseModel):
    """
    The configuration of a fetcher, used as part of a FetchEvent
    Fetch Provider's have their own uniqueue events and configurations.
    Configurations  
    """
    pass

class FetchEvent(BaseModel):
    """
    Event used to describe an queue fetching tasks
    """
    # optional name of the specific event
    name:str = ""
    # A string identifying the fetcher class to use (as registered in the fetcher arsenal)
    fetcher:str
    # The url the event targets for fetching
    url: str
    #  Specific fetcher configuration (overridden by deriving event classes)
    config: FetcherConfig = None

