import asyncio

from pydantic import BaseModel, Field

from opal_common.fetcher.fetch_provider import BaseFetchProvider
from opal_common.fetcher.events import FetcherConfig, FetchEvent


class TestFetcherConfig(FetcherConfig):
    """
    Config for TestFetchProvider, instance of `FetcherConfig`.

    When an OPAL client receives an update, it contains a list of `DataSourceEntry` objects.
    Each `DataSourceEntry` has a `config` key - which is usually an instance of a subclass of `FetcherConfig`.

    When writing a custom provider, you must:
    - derive your class (inherit) from FetcherConfig
    - override the `fetcher` key with your fetcher class name
    - (optional): add any fields relevant to a data entry of your fetcher.
        - In this example: since we pull data from PostgreSQL - we added a `query` key to hold the SQL query.
    """
    fetcher: str = "TestsFetchProvider"
    timeout: int = 10

class TestFetchEvent(FetchEvent):
    fetcher: str = "TestFetchProvider"
    config: TestFetcherConfig = None

class TestFetchProvider(BaseFetchProvider):
    """
    The fetch-provider logic, must inherit from `BaseFetchProvider`.
    """
    ...

    def __init__(self, event: TestFetchEvent) -> None:
        """
        inits your provider class
        """

    def parse_event(self, event: TestFetchEvent) -> TestFetchEvent:
        """
        deserializes the fetch event type from the general `FetchEvent` to your derived fetch event (i.e: `TestFetchEvent`)
        """
        return TestFetchEvent(**event.dict(exclude={"config"}), config = event.config)

    async def _fetch_(self):
        self._event: TestFetchEvent # type casting

        if self._event.config.timeout:
            await asyncio.sleep(self._event.config.timeout)
        else:
            await asyncio.sleep(10)
    async def _process_(self, data):
        """
        optional processing of the data returned by _fetch_().
        must return a jsonable python object (i.e: an object that can be dumped to json,
        e.g: a list or a dict that contains only serializable objects).
        """