"""Pipeline compiler and executor for chaining middlewares around target handlers."""

from __future__ import annotations

import functools
from collections.abc import Sequence
from typing import Any

from framework.context.context import BaleContext
from framework.dispatcher.middleware import BaseMiddleware, HandlerCallable, MiddlewareCallable


class MiddlewarePipeline:
    """
    Constructs and executes the middleware onion around a target handler.
    """

    def __init__(self, middlewares: Sequence[BaseMiddleware | MiddlewareCallable] | None = None) -> None:
        self._middlewares: list[BaseMiddleware | MiddlewareCallable] = list(middlewares or [])

    def add(self, middleware: BaseMiddleware | MiddlewareCallable) -> None:
        """Register a middleware at the end of the chain."""
        self._middlewares.append(middleware)

    def compile(self, target_handler: HandlerCallable) -> HandlerCallable:
        """
        Compile the full pipeline into a single wrapped callable.

        Execution order:
        First registered middleware runs first, entering towards the target handler,
        then exiting in reverse order.
        """
        current_handler: HandlerCallable = target_handler

        for middleware in reversed(self._middlewares):
            current_handler = self._wrap(middleware, current_handler)

        return current_handler

    @staticmethod
    def _wrap(
        middleware: BaseMiddleware | MiddlewareCallable,
        next_handler: HandlerCallable,
    ) -> HandlerCallable:
        @functools.wraps(next_handler)
        async def _layer(event: BaleContext, data: dict[str, Any]) -> Any:
            return await middleware(next_handler, event, data)

        return _layer

    async def execute(
        self,
        target_handler: HandlerCallable,
        event: BaleContext,
        data: dict[str, Any],
    ) -> Any:
        """Convenience method to compile and immediately execute the pipeline."""
        pipeline = self.compile(target_handler)
        return await pipeline(event, data)
