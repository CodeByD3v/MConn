"""Small in-memory limiter for unauthenticated endpoints.

This is intentionally keyed from the socket peer address, never forwarding
headers controlled by a client. It limits abuse before a pairing claim body is
read; it is not a distributed abuse-prevention system.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class FixedWindowLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._seen: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            attempts = self._seen[key]
            cutoff = now - self.window_seconds
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self.limit:
                return False
            attempts.append(now)
            return True
