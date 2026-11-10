"""In-memory FSM storage implementation for testing and development."""

from __future__ import annotations

import copy
from typing import Any

from framework.fsm.key import StorageKey
from framework.fsm.state import State
from framework.fsm.storage.base import BaseStorage


class MemoryStorage(BaseStorage):
    """
    Volatile in-memory implementation of BaseStorage.
    State is cleared on process restart. Ideal for tests or ephemeral state.
    """

    def __init__(self) -> None:
        self._states: dict[StorageKey, str | None] = {}
        self._data: dict[StorageKey, dict[str, Any]] = {}

    def _resolve_state(self, state: str | State | None) -> str | None:
        if isinstance(state, State):
            return state.state
        return state

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        state_str = self._resolve_state(state)
        if state_str is None:
            self._states.pop(key, None)
        else:
            self._states[key] = state_str

    async def get_state(self, key: StorageKey) -> str | None:
        return self._states.get(key)

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        self._data[key] = copy.deepcopy(data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return copy.deepcopy(self._data.get(key, {}))

    async def update_data(
        self,
        key: StorageKey,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        current = await self.get_data(key)
        if data:
            current.update(data)
        if kwargs:
            current.update(kwargs)
        await self.set_data(key, current)
        return copy.deepcopy(current)

    async def clear(self, key: StorageKey) -> None:
        self._states.pop(key, None)
        self._data.pop(key, None)

    async def close(self) -> None:
        self._states.clear()
        self._data.clear()
