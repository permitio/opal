from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from tenacity import (
    _utils,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    wait_random_exponential,
)


class WaitStrategy(str, Enum):
    # Fixed-time waiting between each retry (see https://tenacity.readthedocs.io/en/latest/api.html#tenacity.wait.wait_fixed)
    fixed = "fixed"
    # Exponential backoff (see https://tenacity.readthedocs.io/en/latest/api.html#tenacity.wait.wait_exponential)
    exponential = "exponential"
    # Exponential backoff randomized (see https://tenacity.readthedocs.io/en/latest/api.html#tenacity.wait.wait_random_exponential)
    random_exponential = "random_exponential"


class ConnRetryOptions(BaseModel):
    wait_strategy: WaitStrategy = Field(
        WaitStrategy.fixed,
        description="waiting strategy (e.g. fixed for fixed-time waiting, exponential for exponential back-off) (default fixed)",
    )
    wait_time: float = Field(
        2,
        description="waiting time in seconds (semantic depends on the waiting strategy) (default 2)",
    )
    attempts: int = Field(2, description="number of attempts (default 2)")
    max_wait: float = Field(
        _utils.MAX_WAIT,
        description="max time to wait in total (for exponential strategies only)",
    )

    def toTenacityConfig(self):
        if self.wait_strategy == WaitStrategy.exponential:
            wait = wait_exponential(multiplier=self.wait_time, max=self.max_wait)
        elif self.wait_strategy == WaitStrategy.random_exponential:
            wait = wait_random_exponential(multiplier=self.wait_time, max=self.max_wait)
        else:
            wait = wait_fixed(self.wait_time)
        return dict(wait=wait, stop=stop_after_attempt(self.attempts))
