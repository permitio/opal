from enum import Enum

from pydantic import BaseModel, Field
from tenacity import stop_after_attempt, wait_exponential, wait_fixed


class WaitStrategy(str, Enum):
    # Fixed-time waiting between each retry (see https://tenacity.readthedocs.io/en/latest/api.html#tenacity.wait.wait_fixed)
    fixed = "fixed"
    # Exponential backoff (see https://tenacity.readthedocs.io/en/latest/api.html#tenacity.wait.wait_fixed)
    exponential = "exponential"


class PolicyStoreConnRetryOptions(BaseModel):
    wait_strategy: WaitStrategy = Field(
        WaitStrategy.fixed,
        description="waiting strategy (e.g. fixed for fixed-time waiting, exponential for exponential backoff) (default fixed)",
    )
    wait_time: float = Field(
        2,
        description="waiting time in seconds (semantic depends on the waiting strategy) (default 2)",
    )
    attempts: int = Field(2, description="number of attempts (default 2)")

    def toTenacityConfig(self):
        if self.wait_strategy == WaitStrategy.exponential:
            wait = wait_exponential(multiplier=self.wait_time)
        else:
            wait = wait_fixed(self.wait_time)
        return dict(wait=wait, stop=stop_after_attempt(self.attempts))
