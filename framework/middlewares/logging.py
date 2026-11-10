"""
Structured logging middleware with request tracing and latency measurement.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from framework.context.context import BaleContext
from framework.dispatcher.middleware import BaseMiddleware, HandlerCallable

logger = logging.getLogger("bale.middleware.logging")


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware that generates a unique `trace_id` for each update and logs
    inbound event parameters, execution latency, and completion status.
    """

    def __init__(self, log_level: int = logging.INFO) -> None:
        self.log_level = log_level

    async def __call__(
        self,
        handler: HandlerCallable,
        event: BaleContext,
        data: dict[str, Any],
    ) -> Any:
        trace_id = str(uuid.uuid4())[:8]
        data["trace_id"] = trace_id

        start_time = time.perf_counter()
        logger.log(
            self.log_level,
            "[%s] Incoming %s (update_id=%s, user=%s, chat=%s)",
            trace_id,
            event.event_type,
            event.update_id,
            event.user_id,
            event.chat_id,
        )

        try:
            result = await handler(event, data)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.log(
                self.log_level,
                "[%s] Completed in %.2fms (result=%s)",
                trace_id,
                duration_ms,
                result,
            )
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "[%s] Failed after %.2fms with %s: %s",
                trace_id,
                duration_ms,
                type(exc).__name__,
                exc,
            )
            raise
