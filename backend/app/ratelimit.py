"""Tiny in-process sliding-window rate limiter for the login endpoint.

One uvicorn process (launchd) → in-memory state is sufficient; revisit only if
the app ever runs multi-process (see WISHLIST: slowapi).
"""

import time
from collections import defaultdict, deque
from threading import Lock

WINDOW_SECONDS = 60.0
MAX_ATTEMPTS = 5

_attempts: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def allow(key: str) -> bool:
    """Record an attempt for `key`; False when the window budget is exhausted."""
    now = time.monotonic()
    with _lock:
        window = _attempts[key]
        while window and now - window[0] > WINDOW_SECONDS:
            window.popleft()
        if len(window) >= MAX_ATTEMPTS:
            return False
        window.append(now)
        return True


def reset() -> None:
    with _lock:
        _attempts.clear()
