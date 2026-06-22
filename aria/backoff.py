"""Exponential backoff for reconnect attempts.

Kept as a tiny, pure, fully-testable unit so the live reconnect loop in the CLI
stays trivial. ``next()`` returns the delay to wait before the next attempt, or
``None`` once the attempt budget is exhausted.
"""

from __future__ import annotations

from typing import Optional


class Backoff:
    def __init__(
        self,
        base: float = 1.0,
        factor: float = 2.0,
        cap: float = 30.0,
        max_attempts: int = 6,
    ) -> None:
        self.base = base
        self.factor = factor
        self.cap = cap
        self.max_attempts = max_attempts
        self._n = 0

    def reset(self) -> None:
        """Call after a connection has been successfully established."""
        self._n = 0

    def next(self) -> Optional[float]:
        if self._n >= self.max_attempts:
            return None
        delay = min(self.cap, self.base * (self.factor ** self._n))
        self._n += 1
        return delay
