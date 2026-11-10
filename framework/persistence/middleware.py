"""Unit of Work middleware managing database transaction lifecycle per update."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from framework.context.context import BaleContext
from framework.dispatcher.middleware import BaseMiddleware, HandlerCallable
from framework.persistence.unit_of_work import BaseUnitOfWork

logger = logging.getLogger("bale.middleware.uow")

UoWFactory = Callable[[], BaseUnitOfWork]


class UnitOfWorkMiddleware(BaseMiddleware):
    """
    Middleware that manages transactional lifecycle for each incoming update.

    - Creates a fresh, isolated UnitOfWork instance per request.
    - Injects it into `ctx.data["uow"]` and handler kwargs.
    - Automatically commits changes if handler completes successfully.
    - Automatically rolls back if an unhandled exception escapes.
    """

    def __init__(self, uow_factory: UoWFactory, auto_commit: bool = True) -> None:
        self.uow_factory = uow_factory
        self.auto_commit = auto_commit

    async def __call__(
        self,
        handler: HandlerCallable,
        event: BaleContext,
        data: dict[str, Any],
    ) -> Any:
        uow = self.uow_factory()

        async with uow:
            data["uow"] = uow
            event.data["uow"] = uow

            result = await handler(event, data)

            if self.auto_commit:
                await uow.commit()

            return result
