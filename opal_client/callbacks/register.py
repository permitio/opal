import hashlib
from typing import Dict, Tuple, List, Union, Optional, Generator

from opal_common.logger import logger
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.schemas.data import CallbackEntry
from opal_client.config import opal_client_config


CallbackConfig = Tuple[str, HttpFetcherConfig]


class CallbacksRegister:
    """
    A store for callbacks to other services, invoked on OPA state changes.

    Every time OPAL client successfully finishes a transaction to update OPA state,
    all the callbacks in this register will be called.
    """
    def __init__(self, initial_callbacks: List[Union[str, CallbackConfig]]) -> None:
        self._callbacks: Dict[str, CallbackConfig] = {}
        self._load_initial_callbacks(initial_callbacks)
        logger.info("Callbacks register loaded")

    def _load_initial_callbacks(self, initial_callbacks: List[Union[str, CallbackConfig]]) -> None:
        for callback in initial_callbacks:
            if isinstance(callback, str):
                url = callback
                config = opal_client_config.DEFAULT_UPDATE_CALLBACK_CONFIG
            elif isinstance(callback, CallbackConfig):
                url, config = callback
            else:
                logger.warning(f"Unsupported type for callback config: {type(callback).__name__}")
                continue
            key = self.calc_hash(url, config)
            self._register(key, url, config)

    def _register(self, key: str, url: str, config: HttpFetcherConfig):
        self._callbacks[key] = (url, config)

    def calc_hash(self, url: str, config: HttpFetcherConfig) -> str:
        """
        gets a unique hash key from a callback url and config.
        """
        m = hashlib.sha256()
        m.update(url)
        m.update(config.json().encode())
        return m.hexdigest()

    def get(self, key: str) -> Optional[CallbackEntry]:
        """
        gets a registered callback by its key, or None if no such key found in register.
        """
        callback = self._callbacks.get(key, None)
        if callback is None:
            return None
        (url, config) = callback
        return CallbackEntry(key=key, url=url, config=config)

    def put(self, url: str, config: Optional[HttpFetcherConfig] = None, key: Optional[str] = None):
        """
        puts a callback in the register.
        if no config is provided, the default callback config will be used.
        if no key is provided, the key will be calculated by hashing the url and config.
        """
        callback_config = config or opal_client_config.DEFAULT_UPDATE_CALLBACK_CONFIG
        callback_key = key or self.calc_hash(url, callback_config)
        self._register(callback_key, url, callback_config)

    def all(self) -> Generator[CallbackEntry, None, None]:
        """
        a generator yielding all the callback configs currently registered.

        Yields:
            the next callback config found
        """
        for key, (url, config) in iter(self._callbacks.items()):
            yield CallbackEntry(key=key, url=url, config=config)