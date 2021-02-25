from .events import FetchEvent
from tenacity import retry, wait, stop
import tenacity

from .logger import get_logger
logger = get_logger("providers")


class BaseFetchProvider:
    """
    Base class for data fetching providers.
     - Override self._fetch_ to implement fetching
     - call self.fetch() to retrive data (wrapped in retries and safe execution guards)
    """

    @staticmethod
    def logerror(retry_state: tenacity.RetryCallState):
        logger.exception(retry_state.outcome.exception())

    DEFAULT_RETRY_CONFIG = {
        'wait': wait.wait_random_exponential(),
        "stop": stop.stop_after_attempt(200),
        'reraise': True,
        "retry_error_callback": logerror
    }

    def __init__(self, event: FetchEvent, retry_config=None) -> None:
        self._event = event
        self._url = event.url
        self._retry_config = retry_config if retry_config is not None else self.DEFAULT_RETRY_CONFIG

    async def fetch(self):
        """
        Call self._fetch_ with a retry mechanism
        """
        return await retry(**self._retry_config)(self._fetch_)()

    async def _fetch_():
        pass


