"""Base contracts for middlewares in the dispatching pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from framework.context.context import BaleContext

# Handler function signature: receives the context and dependency dictionary
HandlerCallable = Callable[[BaleContext, dict[str, Any]], Awaitable[Any]]

# Middleware function signature
MiddlewareCallable = Callable[[HandlerCallable, BaleContext, dict[str, Any]], Awaitable[Any]]


class BaseMiddleware(ABC):
    """
    Abstract middleware following the Onion / Chain of Responsibility pattern.

    Subclasses must implement __call__ and invoke `await handler(event, data)`
    to pass control to the inner layers of the pipeline.
    """

    @abstractmethod
    async def __call__(
        self,
        handler: HandlerCallable,
        event: BaleContext,
        data: dict[str, Any],
    ) -> Any:
        """
        Process the incoming context before and/or after downstream handlers.

        :param handler: Next callable in the pipeline (next middleware or target handler).
        :param event: The strongly typed BaleContext.
        :param data: Mutable dictionary holding dependencies, database sessions, state, etc.
        :return: Result from the handler execution.
        """
        raise NotImplementedError
