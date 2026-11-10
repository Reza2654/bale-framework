"""
Sliding-window in-memory rate limiter middleware per user or chat.
"""

from __future__ import annotations

import collections
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from framework.context.context import BaleContext
from framework.dispatcher.middleware import BaseMiddleware, HandlerCallable

logger = logging.getLogger("bale.middleware.rate_limit")

ThrottleHandler = Callable[[BaleContext, dict[str, Any]], Awaitable[None]]


class RateLimitMiddleware(BaseMiddleware):
    """
    In-memory sliding-window rate limiter.

    Guards bot handlers against flooding by limiting each user (or chat)
    to a maximum number of updates within a sliding time window.
    """

    def __init__(
        self,
        rate: int = 5,
        period: float = 1.0,
        warn_user: bool = True,
        warn_cooldown: float = 3.0,
        warn_message: str = "⏳ You are sending requests too quickly. Please slow down.",
        on_throttled: ThrottleHandler | None = None,
    ) -> None:
        self.rate = rate
        self.period = period
        self.warn_user = warn_user
        self.warn_cooldown = warn_cooldown
        self.warn_message = warn_message
        self.on_throttled = on_throttled

        # Mapping of identifier -> deque of timestamps
        self._history: dict[int | str, collections.deque[float]] = {}
        # Mapping of identifier -> last warning timestamp
        self._last_warning: dict[int | str, float] = {}
        self._cleanup_counter = 0

    def _get_key(self, event: BaleContext) -> int | str | None:
        """Resolve identifier (prefers user_id, falls back to chat_id)."""
        return event.user_id or event.chat_id

    def _cleanup_stale(self, now: float) -> None:
        """Periodically purge entries with expired timestamps to prevent memory leakage."""
        cutoff = now - self.period
        stale_keys = [
            k for k, timestamps in self._history.items()
            if not timestamps or timestamps[-1] < cutoff
        ]
        for k in stale_keys:
            del self._history[k]
            self._last_warning.pop(k, None)

    async def __call__(
        self,
        handler: HandlerCallable,
        event: BaleContext,
        data: dict[str, Any],
    ) -> Any:
        key = self._get_key(event)
        if key is None:
            # Cannot identify entity; pass through
            return await handler(event, data)

        now = time.monotonic()

        # Housekeeping every 500 requests
        self._cleanup_counter += 1
        if self._cleanup_counter >= 500:
            self._cleanup_counter = 0
            self._cleanup_stale(now)

        if key not in self._history:
            self._history[key] = collections.deque()

        timestamps = self._history[key]
        cutoff = now - self.period

        # Pop timestamps outside the current window
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        # Check if rate limit is exceeded
        if len(timestamps) >= self.rate:
            logger.warning(
                "Rate limit exceeded for entity %s (count: %d >= limit: %d in %.1fs)",
                key,
                len(timestamps),
                self.rate,
                self.period,
            )

            # Trigger custom throttling hook if provided
            if self.on_throttled is not None:
                try:
                    await self.on_throttled(event, data)
                except Exception as err:
                    logger.error("Error in on_throttled hook: %s", err)

            # Warn user if cooldown permits
            if self.warn_user:
                last_warn = self._last_warning.get(key, 0.0)
                if now - last_warn >= self.warn_cooldown:
                    self._last_warning[key] = now
                    try:
                        if event.callback_query:
                            await event.answer(text=self.warn_message, show_alert=True)
                        else:
                            await event.send(text=self.warn_message)
                    except Exception as warn_err:
                        logger.debug("Failed to send rate limit warning: %s", warn_err)

            # Drop the update
            return None

        # Record this request timestamp and proceed
        timestamps.append(now)
        return await handler(event, data)
