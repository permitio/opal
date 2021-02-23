import requests
from .events import FetchEvent

class BaseFetchProvider:

    def __init__(self, event:FetchEvent) -> None:
        self._url = event.url

    async def fetch(self):
        pass


class HttpGetFetchProvider(BaseFetchProvider):
    pass

    def __init__(self, event:FetchEvent) -> None:
        super().__init__(event)

    def fetch(self):
        return requests.get(self._url)


class RestfulFetchProvider(BaseFetchProvider):
    pass

    def __init__(self, event:FetchEvent) -> None:
        super().__init__(event)




