"""Generic abstract repository contract for clean persistence isolation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

EntityType = TypeVar("EntityType")
IdType = TypeVar("IdType")


class BaseRepository(ABC, Generic[EntityType, IdType]):
    """
    Abstract generic repository port.

    Decouples domain services and handlers from specific database technologies
    (SQLAlchemy, Tortoise, Motor, Redis, etc.).
    """

    @abstractmethod
    async def get(self, entity_id: IdType) -> EntityType | None:
        """Fetch a single entity by its unique identifier."""
        raise NotImplementedError

    @abstractmethod
    async def add(self, entity: EntityType) -> EntityType:
        """Persist a new domain entity."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, entity: EntityType) -> EntityType:
        """Update an existing persisted entity."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, entity_id: IdType) -> bool:
        """Remove an entity by identifier. Returns True if deleted."""
        raise NotImplementedError

    @abstractmethod
    async def list(
        self,
        offset: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> list[EntityType]:
        """List entities matching optional search filters."""
        raise NotImplementedError
