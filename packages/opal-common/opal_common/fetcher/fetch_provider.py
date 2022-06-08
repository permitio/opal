from tenacity import retry, stop, wait

from .events import FetchEvent
from .logger import get_logger

logger = get_logger("opal.providers")


class BaseFetchProvider:
    """Base class for data fetching providers.

    - Override self._fetch_ to implement fetching
    - call self.fetch() to retrive data (wrapped in retries and safe execution guards)
    - override __aenter__ and __aexit__ for async context
    """

    DEFAULT_RETRY_CONFIG = {
        "wait": wait.wait_random_exponential(),
        "stop": stop.stop_after_attempt(200),
        "reraise": True,
    }

    def __init__(self, event: FetchEvent, retry_config=None) -> None:
        """
        Args:
            event (FetchEvent): the event desciring what we should fetch
            retry_config (dict): Tenacity.retry config (@see https://tenacity.readthedocs.io/en/latest/api.html#retry-main-api) for retrying fetching
        """
        # convert the event as needed and save it
        self._event = self.parse_event(event)
        self._url = event.url
        self._retry_config = (
            retry_config if retry_config is not None else self.DEFAULT_RETRY_CONFIG
        )

    def parse_event(self, event: FetchEvent) -> FetchEvent:
        """Parse the event (And config within it) into the right object type.

        Args:
            event (FetchEvent): the event to be parsed

        Returns:
            FetchEvent: an event deriving from FetchEvent
        """
        return event

    async def fetch(self):
        """Fetch and return data.

        Calls self._fetch_ with a retry mechanism
        """
        attempter = retry(**self._retry_config)(self._fetch_)
        res = await attempter()
        return res

    async def process(self, data):
        try:
            return await self._process_(data)
        except:
            logger.exception("Failed to process fetched data")
            raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type=None, exc_val=None, tb=None):
        pass

    async def _fetch_(self):
        """Internal fetch operation called by self.fetch() Override this method
        to implement a new fetch provider."""
        pass

    async def _process_(self, data):
        return data

    def set_retry_config(self, retry_config: dict):
        """Set the configuration for retrying failed fetches.

        @see self.DEFAULT_RETRY_CONFIG

        Args:
            retry_config (dict): Tenacity retry config
        """
        self._retry_config = retry_config
