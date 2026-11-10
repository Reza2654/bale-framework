"""Abstract Unit of Work contract for atomic multi-repository operations."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Self

logger = logging.getLogger("bale.uow")


class BaseUnitOfWork(ABC):
    """
    Abstract Unit of Work (UoW) port.

    Coordinates database transactions across one or more repositories,
    guaranteeing atomic commits and automatic rollbacks on error.
    """

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        if exc_type is not None:
            logger.debug("Exception detected within UnitOfWork. Rolling back transaction: %s", exc_val)
            await self.rollback()
        await self.close()

    @abstractmethod
    async def commit(self) -> None:
        """Commit active changes to the database."""
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback active transaction."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release database connection/session resources back to the pool."""
        raise NotImplementedError
