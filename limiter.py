import asyncio
import time
from collections import defaultdict

import config


class ConnectionLimiter:

    def __init__(self):
        self._counts: dict[int, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def acquire(self, user_id: int) -> bool:
        async with self._lock:
            if self._counts[user_id] >= config.WS_MAX_CONNECTIONS_PER_USER:
                return False
            self._counts[user_id] += 1
            return True

    async def release(self, user_id: int) -> None:
        async with self._lock:
            self._counts[user_id] = max(0, self._counts[user_id] - 1)


class MessageRateLimiter:

    def __init__(self, max_messages: int = 30, window_seconds: int = 60):
        self.max_messages   = max_messages
        self.window_seconds = window_seconds
        self._history: dict[int, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, user_id: int) -> bool:
        async with self._lock:
            now    = time.monotonic()
            cutoff = now - self.window_seconds
            self._history[user_id] = [
                t for t in self._history[user_id] if t > cutoff
            ]
            if len(self._history[user_id]) >= self.max_messages:
                return False
            self._history[user_id].append(now)
            return True


connection_limiter    = ConnectionLimiter()
message_rate_limiter  = MessageRateLimiter(max_messages=30, window_seconds=60)