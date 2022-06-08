import hashlib
from typing import Dict, Generator, List, Optional, Tuple, Union

from opal_client.config import opal_client_config
from opal_common.fetcher.providers.http_fetch_provider import HttpFetcherConfig
from opal_common.logger import logger
from opal_common.schemas.data import CallbackEntry

CallbackConfig = Tuple[str, HttpFetcherConfig]


class CallbacksRegister:
    """A store for callbacks to other services, invoked on OPA state changes.

    Every time OPAL client successfully finishes a transaction to update
    OPA state, all the callbacks in this register will be called.
    """

    def __init__(
        self, initial_callbacks: Optional[List[Union[str, CallbackConfig]]] = None
    ) -> None:
        self._callbacks: Dict[str, CallbackConfig] = {}
        if initial_callbacks is not None:
            self._load_initial_callbacks(initial_callbacks)
        logger.info("Callbacks register loaded")

    def _load_initial_callbacks(
        self, initial_callbacks: List[Union[str, CallbackConfig]]
    ) -> None:
        normalized_callbacks = self.normalize_callbacks(initial_callbacks)
        for callback in normalized_callbacks:
            url, config = callback
            key = self.calc_hash(url, config)
            self._register(key, url, config)

    def normalize_callbacks(
        self, callbacks: List[Union[str, CallbackConfig]]
    ) -> List[CallbackConfig]:
        normalized_callbacks = []
        for callback in callbacks:
            if isinstance(callback, str):
                url = callback
                config = opal_client_config.DEFAULT_UPDATE_CALLBACK_CONFIG
                normalized_callbacks.append((url, config))
            elif isinstance(callback, CallbackConfig):
                normalized_callbacks.append(callback)
            else:
                logger.warning(
                    f"Unsupported type for callback config: {type(callback).__name__}"
                )
                continue
        return normalized_callbacks

    def _register(self, key: str, url: str, config: HttpFetcherConfig):
        self._callbacks[key] = (url, config)

    def calc_hash(self, url: str, config: HttpFetcherConfig) -> str:
        """gets a unique hash key from a callback url and config."""
        m = hashlib.sha256()
        m.update(url.encode())
        m.update(config.json().encode())
        return m.hexdigest()

    def get(self, key: str) -> Optional[CallbackEntry]:
        """gets a registered callback by its key, or None if no such key found
        in register."""
        callback = self._callbacks.get(key, None)
        if callback is None:
            return None
        (url, config) = callback
        return CallbackEntry(key=key, url=url, config=config)

    def put(
        self,
        url: str,
        config: Optional[HttpFetcherConfig] = None,
        key: Optional[str] = None,
    ) -> str:
        """puts a callback in the register.

        if no config is provided, the default callback config will be
        used. if no key is provided, the key will be calculated by
        hashing the url and config.
        """
        default_config = opal_client_config.DEFAULT_UPDATE_CALLBACK_CONFIG
        if isinstance(default_config, dict):
            default_config = HttpFetcherConfig(**default_config)

        callback_config = config or default_config
        auto_key = self.calc_hash(url, callback_config)
        callback_key = key or auto_key
        # if the same callback is already registered with another key - remove that callback.
        # there is no point in calling the same callback twice.
        self.remove(auto_key)
        # register the callback under the intended key (auto-generated or provided)
        self._register(callback_key, url, callback_config)
        return callback_key

    def remove(self, key: str):
        """removes a callback from the register, if exists."""
        if key in self._callbacks:
            del self._callbacks[key]

    def all(self) -> Generator[CallbackEntry, None, None]:
        """a generator yielding all the callback configs currently registered.

        Yields:
            the next callback config found
        """
        for key, (url, config) in iter(self._callbacks.items()):
            yield CallbackEntry(key=key, url=url, config=config)
