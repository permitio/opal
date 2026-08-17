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

    def worstCaseTotalWait(self) -> float:
        """Upper bound (seconds) on the time this policy can spend *waiting*.

        Callers use it to size a wall-clock stop condition without truncating a
        retry budget the operator asked for.

        This is the exact sum of the individual waits, not `attempts x max_wait`:
        `max_wait` defaults to tenacity's MAX_WAIT (~4.6e18), so the coarse
        estimate would be astronomically large for anyone who selects an
        exponential strategy without pinning `max_wait`, and a bound derived
        from it would be no bound at all.

        `attempts` attempts are separated by `attempts - 1` waits. Once the
        doubling reaches `max_wait` every remaining wait is `max_wait`, so we
        add them in one step and stop doubling -- both because it is cheaper and
        because `wait_time * 2 ** i` raises OverflowError past i == 1023, which
        a large `attempts` would otherwise hit at client startup.
        """
        n_waits = max(self.attempts - 1, 0)
        if self.wait_strategy not in (
            WaitStrategy.exponential,
            WaitStrategy.random_exponential,
        ):
            return float(n_waits * self.wait_time)

        total = 0.0
        wait = float(self.wait_time)
        for i in range(n_waits):
            if wait >= self.max_wait:
                total += (n_waits - i) * self.max_wait
                break
            total += wait
            wait *= 2.0
        return total

    def toTenacityConfig(self):
        if self.wait_strategy == WaitStrategy.exponential:
            wait = wait_exponential(multiplier=self.wait_time, max=self.max_wait)
        elif self.wait_strategy == WaitStrategy.random_exponential:
            wait = wait_random_exponential(multiplier=self.wait_time, max=self.max_wait)
        else:
            wait = wait_fixed(self.wait_time)
        return dict(wait=wait, stop=stop_after_attempt(self.attempts))
