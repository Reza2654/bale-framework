"""Abstract storage port for Finite State Machine persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from framework.fsm.key import StorageKey
from framework.fsm.state import State


class BaseStorage(ABC):
    """
    Abstract port for persisting FSM states and arbitrary context data.

    Decouples state storage from specific backends (Memory, SQLite, Redis).
    """

    @abstractmethod
    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        """Set the active state for the given storage key."""
        raise NotImplementedError

    @abstractmethod
    async def get_state(self, key: StorageKey) -> str | None:
        """Get the active state string for the given storage key."""
        raise NotImplementedError

    @abstractmethod
    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        """Overwrite the context data dictionary for the given storage key."""
        raise NotImplementedError

    @abstractmethod
    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        """Get the context data dictionary for the given storage key."""
        raise NotImplementedError

    @abstractmethod
    async def update_data(
        self,
        key: StorageKey,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update and return the merged context data dictionary."""
        raise NotImplementedError

    @abstractmethod
    async def clear(self, key: StorageKey) -> None:
        """Reset state and wipe all stored data for the given key."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release underlying connections or storage resources."""
        raise NotImplementedError
