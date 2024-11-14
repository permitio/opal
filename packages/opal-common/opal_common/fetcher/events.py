from typing import List, Optional

from pydantic import BaseModel, Field


class FetcherConfig(BaseModel):
    """The configuration of a fetcher, used as part of a FetchEvent Fetch
    Provider's have their own uniqueue events and configurations.

    Configurations
    """

    fetcher: Optional[str] = Field(
        None,
        description="indicates to OPAL client that it should use a custom FetcherProvider to fetch the data",
    )


class FetchEvent(BaseModel):
    """Event used to describe an queue fetching tasks Design note -

    By using a Pydantic model - we can create a potentially transfer FetchEvents to be handled by other network nodes (perhaps via RPC)
    """

    # Event id to be filled by the engine
    id: str = None
    # optional name of the specific event
    name: str = None
    # A string identifying the fetcher class to use (as registered in the fetcher register)
    fetcher: str
    # The url the event targets for fetching
    url: str
    # Specific fetcher configuration (overridden by deriving event classes (FetcherConfig)
    config: dict = None
    # Tenacity.retry - Override default retry configuration for this event
    retry: dict = None
