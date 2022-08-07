from enum import Enum

from pydantic import BaseModel, Field


class WaitStrategy(str, Enum):
    fixed = "fixed"
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
