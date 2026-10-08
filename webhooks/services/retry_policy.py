import random
from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    base_seconds: float
    max_seconds: float

    @classmethod
    def from_settings(cls) -> "RetryPolicy":
        return cls(
            max_attempts=settings.RELAY_MAX_ATTEMPTS,
            base_seconds=settings.RELAY_RETRY_BASE_SECONDS,
            max_seconds=settings.RELAY_RETRY_MAX_SECONDS,
        )

    def delay_after(self, attempt: int, rng: Callable[[], float] = random.random) -> float | None:
        """
        Seconds to wait after the given failed attempt, or None to give up (dead letter).

        Exponential backoff with "equal jitter": half of the window is fixed and half is random.
        The randomness spreads out retries from many deliveries that failed at the same moment,
        and the fixed half avoids a retry right after the failure.
        """
        if attempt >= self.max_attempts:
            return None
        ceiling = min(self.max_seconds, self.base_seconds * 2 ** (attempt - 1))
        return ceiling / 2 + rng() * ceiling / 2
