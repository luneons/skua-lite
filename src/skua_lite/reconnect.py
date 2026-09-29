"""Self-healing reconnect policy.

Pure retry arithmetic kept apart from the socket so the schedule is
deterministic and testable. The runner owns the actual reconnect attempt; this
module only answers *when* to try again and *whether* to keep trying, which
stops a dead session from hammering the login server forever.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ReconnectPolicy:
    """Bounded exponential backoff for relogin attempts.

    ``base_delay`` seconds before the first retry, multiplied by ``factor`` per
    further attempt, never exceeding ``max_delay``, and never more than
    ``max_attempts`` retries in total.
    """

    base_delay: float = 2.0
    factor: float = 2.0
    max_delay: float = 60.0
    max_attempts: int = 5

    def __post_init__(self) -> None:
        if self.base_delay <= 0:
            raise ValueError("base_delay harus > 0")
        if self.factor <= 1:
            raise ValueError("factor harus > 1")
        if self.max_delay <= 0:
            raise ValueError("max_delay harus > 0")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay tidak boleh lebih kecil dari base_delay")
        if self.max_attempts < 1:
            raise ValueError("max_attempts harus >= 1")

    def delay_for(self, attempt: int) -> float:
        """Seconds to wait before retry number ``attempt`` (1 = first retry)."""
        step = max(0, int(attempt) - 1)
        return min(float(self.max_delay), float(self.base_delay) * (self.factor ** step))

    def should_retry(self, attempt: int) -> bool:
        """True while ``attempt`` failed tries still leave an attempt unused."""
        return int(attempt) < int(self.max_attempts)
