"""FSMContext wrapper bound to specific storage key."""

from __future__ import annotations

from typing import Any

from framework.fsm.key import StorageKey
from framework.fsm.state import State
from framework.fsm.storage.base import BaseStorage


class FSMContext:
    """
    Contextual wrapper providing ergonomic state and data mutation methods
    for a specific user/chat session.
    """

    def __init__(self, storage: BaseStorage, key: StorageKey) -> None:
        self.storage = storage
        self.key = key

    async def set_state(self, state: str | State | None = None) -> None:
        """Update the active state."""
        await self.storage.set_state(self.key, state)

    async def get_state(self) -> str | None:
        """Retrieve the currently active state string."""
        return await self.storage.get_state(self.key)

    async def set_data(self, data: dict[str, Any]) -> None:
        """Overwrite the context data dictionary."""
        await self.storage.set_data(self.key, data)

    async def get_data(self) -> dict[str, Any]:
        """Fetch stored context data."""
        return await self.storage.get_data(self.key)

    async def update_data(
        self,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update and return the merged context data."""
        return await self.storage.update_data(self.key, data=data, **kwargs)

    async def clear(self) -> None:
        """Reset state and wipe all stored data for this session."""
        await self.storage.clear(self.key)

    def __repr__(self) -> str:
        return f"FSMContext(key={self.key.to_string()!r})"
