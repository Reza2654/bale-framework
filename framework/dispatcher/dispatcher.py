"""
Central Dispatcher engine responsible for update distribution and middleware execution.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol

from framework.context.context import BaleContext
from framework.dispatcher.middleware import BaseMiddleware, HandlerCallable, MiddlewareCallable
from framework.dispatcher.pipeline import MiddlewarePipeline
from framework.fsm.context import FSMContext
from framework.fsm.key import StorageKey
from framework.fsm.storage.base import BaseStorage

if TYPE_CHECKING:
    from framework.client.client import BaleBotClient

logger = logging.getLogger("bale.dispatcher")


class Routable(Protocol):
    """Protocol satisfied by modular Routers in Pillar 3."""

    async def feed(self, ctx: BaleContext, data: dict[str, Any]) -> bool:
        """Attempt to match and handle the incoming update context."""
        ...


class Dispatcher:
    """
    Central event dispatcher for Bale Bot updates.

    Acts as the primary `UpdateConsumer` callable for Ingestion engines
    (LongPollingEngine or WebhookEngine).

    Responsibilities:
    - Maintains the global middleware pipeline.
    - Mounts and orchestrates modular sub-routers.
    - Wraps raw updates in strongly typed `BaleContext`.
    """

    def __init__(
        self,
        client: BaleBotClient,
        storage: BaseStorage | None = None,
        bot_id: int | str = "bale_bot",
        workflow_data: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.storage = storage
        self.bot_id = bot_id
        self.workflow_data: dict[str, Any] = workflow_data or {}
        self._middlewares: list[BaseMiddleware | MiddlewareCallable] = []
        self._routers: list[Routable] = []
        self._compiled_pipeline: HandlerCallable | None = None

    def add_middleware(self, middleware: BaseMiddleware | MiddlewareCallable) -> None:
        """Register a middleware to the outer pipeline."""
        self._middlewares.append(middleware)
        self._compiled_pipeline = None  # Invalidate cached compiled pipeline

    def include_router(self, router: Routable) -> None:
        """Mount a sub-router into the dispatcher."""
        self._routers.append(router)

    def include_routers(self, *routers: Routable) -> None:
        """Mount multiple sub-routers in order of evaluation."""
        for r in routers:
            self.include_router(r)

    async def __call__(self, raw_update: dict[str, Any]) -> Any:
        """Convenience invocation to satisfy `UpdateConsumer` signature."""
        return await self.feed_update(raw_update)

    async def feed_update(self, raw_update: dict[str, Any]) -> Any:
        """
        Process a single raw update received from the ingestion engine.

        Constructs the execution context and drives the update through
        the compiled middleware pipeline into the router tree.
        """
        # Create execution context with a shallow copy of shared workflow data
        context_data = dict(self.workflow_data)
        ctx = BaleContext(
            update=raw_update,
            client=self.client,
            data=context_data,
        )

        # Automatically bind FSMContext if storage is configured
        if self.storage and ctx.chat_id is not None and ctx.user_id is not None:
            storage_key = StorageKey(
                bot_id=self.bot_id,
                chat_id=ctx.chat_id,
                user_id=ctx.user_id,
            )
            fsm_ctx = FSMContext(storage=self.storage, key=storage_key)
            context_data["state"] = fsm_ctx
            ctx.data["state"] = fsm_ctx

        if self._compiled_pipeline is None:
            pipeline = MiddlewarePipeline(self._middlewares)
            self._compiled_pipeline = pipeline.compile(self._dispatch_to_routers)

        return await self._compiled_pipeline(ctx, context_data)

    async def _dispatch_to_routers(self, ctx: BaleContext, data: dict[str, Any]) -> bool:
        """Iterate over registered routers until one successfully handles the update."""
        for router in self._routers:
            try:
                handled = await router.feed(ctx, data)
                if handled:
                    return True
            except Exception as exc:
                logger.exception(
                    "Unhandled exception in router %s while processing update %s: %s",
                    router,
                    ctx.update_id,
                    exc,
                )
                raise

        logger.debug(
            "Update %s (type=%s) was ignored (no router matched).",
            ctx.update_id,
            ctx.event_type,
        )
        return False
