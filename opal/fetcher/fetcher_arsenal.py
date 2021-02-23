from .data_fetcher import HttpGetFetchProvider, RestfulFetchProvider, BaseFetchProvider
from .events import FetchEvent



class FetcherArsenal:

    BASIC_CONFIG = {
        "HttpGetFetchProvider": HttpGetFetchProvider,
        "RestfulFetchProvider": RestfulFetchProvider
    }

    def __init__(self, config=None) -> None:
        self._config = config or self.BASIC_CONFIG

    def get_fetcher(self, name, event)->BaseFetchProvider:
        return self._config.get(name)(event)

    def get_fetcher_for_event(self, event:FetchEvent)->BaseFetchProvider:
        return self.get_fetcher(event.fetcher, event)
        