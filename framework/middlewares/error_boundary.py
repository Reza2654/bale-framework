"""
Error boundary middleware to prevent worker termination and log unhandled exceptions.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from framework.context.context import BaleContext
from framework.dispatcher.middleware import BaseMiddleware, HandlerCallable

logger = logging.getLogger("bale.middleware.error_boundary")

ExceptionHandler = Callable[[Exception, BaleContext, dict[str, Any]], Awaitable[None]]


class ErrorBoundaryMiddleware(BaseMiddleware):
    """
    Catches any unhandled exceptions raised inside downstream middlewares or handlers.

    Features:
    - Isolates failures so worker tasks and ingestion loops remain healthy.
    - Optionally replies to the user with a localized, user-safe error message.
    - Pluggable external error reporter callback (e.g. Sentry, Datadog).
    """

    def __init__(
        self,
        notify_user: bool = True,
        user_message: str = "⚠️ An unexpected error occurred while processing your request. Please try again later.",
        on_error: ExceptionHandler | None = None,
    ) -> None:
        self.notify_user = notify_user
        self.user_message = user_message
        self.on_error = on_error

    async def __call__(
        self,
        handler: HandlerCallable,
        event: BaleContext,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:
            trace_id = data.get("trace_id", "unknown")
            logger.exception(
                "[%s] Uncaught exception processing update %s (user=%s, chat=%s): %s",
                trace_id,
                event.update_id,
                event.user_id,
                event.chat_id,
                exc,
            )

            # Trigger custom reporter callback (e.g., Sentry) if provided
            if self.on_error is not None:
                try:
                    await self.on_error(exc, event, data)
                except Exception as report_err:
                    logger.error("[%s] Exception reporter callback failed: %s", trace_id, report_err)

            # Attempt to inform the user if chat_id exists and notification is enabled
            if self.notify_user and event.chat_id is not None:
                try:
                    if event.callback_query:
                        await event.answer(
                            text="An error occurred while processing this action.",
                            show_alert=True,
                        )
                    else:
                        await event.send(text=self.user_message)
                except Exception as notify_err:
                    logger.warning("[%s] Failed to deliver error notification to user: %s", trace_id, notify_err)

            # Return None to indicate the failure was absorbed and handled
            return None
