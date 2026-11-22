"""Protection for a public preview: an access code and per-client rate limits.

Single-owner demo, so one shared access code (ACCESS_CODE) stands in for login. Compared in
constant time. Without a code set (local use), the API is open, as before.
"""

from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "/runs": (5, 60),  # each run may call the model for every invoice
    "/ask": (10, 60),  # two model calls per question
    "/decision": (60, 60),
}


def code_ok(header: str | None, code: str) -> bool:
    if not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header.removeprefix("Bearer ").encode(), code.encode())


class RateLimiter:
    def __init__(
        self,
        limits: dict[str, tuple[int, int]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limits = DEFAULT_LIMITS if limits is None else limits
        self.clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def bucket(self, path: str) -> str | None:
        for key in self.limits:
            if path == key or path.endswith(key):
                return key
        return None

    def allow(self, client: str, path: str) -> bool:
        key = self.bucket(path)
        if key is None:
            return True
        limit, window = self.limits[key]
        now = self.clock()
        with self._lock:
            q = self._hits[(client, key)]
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True
