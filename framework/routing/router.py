"""Modular Router supporting sub-router trees and event routing."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from framework.context.context import BaleContext
from framework.routing.filters.base import BaseFilter
from framework.routing.handler import HandlerRecord

logger = logging.getLogger("bale.routing.router")


class Router:
    """
    Modular event router.

    Can be nested hierarchically to structure large bot applications into
    isolated feature modules (e.g. auth_router, settings_router, order_router).
    """

    def __init__(self, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__
        self.sub_routers: list[Router] = []
        self._handlers: dict[str, list[HandlerRecord]] = {
            "message": [],
            "callback_query": [],
            "*": [],
        }

    def include_router(self, router: Router) -> None:
        """Attach a sub-router to this router."""
        if router is self:
            raise ValueError("Cannot include router into itself.")
        self.sub_routers.append(router)

    def include_routers(self, *routers: Router) -> None:
        """Attach multiple sub-routers in order."""
        for r in routers:
            self.include_router(r)

    def register_handler(
        self,
        event_type: str,
        callback: Callable[..., Awaitable[Any]],
        *filters: BaseFilter | Callable[[BaleContext], Awaitable[bool]],
    ) -> None:
        """Register a handler record under the given event type bucket."""
        record = HandlerRecord(callback=callback, filters=list(filters))
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(record)

    # ================= Decorators =================

    def message(
        self,
        *filters: BaseFilter | Callable[[BaleContext], Awaitable[bool]],
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Decorator to register a message event handler."""

        def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            self.register_handler("message", func, *filters)
            return func

        return decorator

    def callback_query(
        self,
        *filters: BaseFilter | Callable[[BaleContext], Awaitable[bool]],
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Decorator to register a callback_query event handler."""

        def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            self.register_handler("callback_query", func, *filters)
            return func

        return decorator

    def update(
        self,
        *filters: BaseFilter | Callable[[BaleContext], Awaitable[bool]],
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Decorator to register a catch-all update handler."""

        def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            self.register_handler("*", func, *filters)
            return func

        return decorator

    # ================= Dispatch logic =================

    async def feed(self, ctx: BaleContext, data: dict[str, Any]) -> bool:
        """
        Process the incoming context against this router's handlers and sub-routers.

        Returns True if a matching handler was executed, False otherwise.
        """
        event_type = ctx.event_type

        # 1. Search type-specific handlers
        target_handlers = self._handlers.get(event_type, [])
        for handler in target_handlers:
            matched, filter_data = await handler.check(ctx)
            if matched:
                logger.debug("[%s] Handler '%s' matched for update %s", self.name, handler.callback.__name__, ctx.update_id)
                await handler.call(ctx, {**data, **filter_data})
                return True

        # 2. Search wildcard handlers
        wildcard_handlers = self._handlers.get("*", [])
        for handler in wildcard_handlers:
            matched, filter_data = await handler.check(ctx)
            if matched:
                logger.debug("[%s] Wildcard handler '%s' matched for update %s", self.name, handler.callback.__name__, ctx.update_id)
                await handler.call(ctx, {**data, **filter_data})
                return True

        # 3. Propagate to sub-routers
        for sub_router in self.sub_routers:
            handled = await sub_router.feed(ctx, data)
            if handled:
                return True

        return False

    def __repr__(self) -> str:
        handlers_count = sum(len(h) for h in self._handlers.values())
        return f"Router(name={self.name!r}, handlers={handlers_count}, sub_routers={len(self.sub_routers)})"
