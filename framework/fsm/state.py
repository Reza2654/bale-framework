"""
State and StatesGroup primitives for defining Finite State Machines.
"""

from __future__ import annotations

from typing import Any


class State:
    """
    Represents an individual discrete state in a finite state machine.
    """

    def __init__(self, state_name: str | None = None, group_name: str | None = None) -> None:
        self._state_name = state_name
        self._group_name = group_name

    @property
    def state(self) -> str | None:
        if self._state_name is None:
            return None
        if self._group_name:
            return f"{self._group_name}:{self._state_name}"
        return self._state_name

    def _set_parent(self, group_name: str, state_name: str) -> None:
        self._group_name = group_name
        self._state_name = state_name

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, State):
            return self.state == other.state
        if isinstance(other, str):
            return self.state == other
        if other is None:
            return self.state is None
        return False

    def __hash__(self) -> int:
        return hash(self.state)

    def __repr__(self) -> str:
        return f"State({self.state!r})"


class StatesGroupMeta(type):
    """Metaclass that inspects attributes and automatically binds state names to the group."""

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
    ) -> StatesGroupMeta:
        states: list[State] = []
        cls = super().__new__(mcs, name, bases, namespace)

        for attr_name, attr_val in namespace.items():
            if isinstance(attr_val, State):
                attr_val._set_parent(group_name=name, state_name=attr_name)
                states.append(attr_val)

        setattr(cls, "_all_states", tuple(states))
        return cls

    def __contains__(cls, item: Any) -> bool:
        if isinstance(item, State):
            return item in getattr(cls, "_all_states", ())
        if isinstance(item, str):
            return any(s.state == item for s in getattr(cls, "_all_states", ()))
        return False

    def __iter__(cls) -> Any:
        return iter(getattr(cls, "_all_states", ()))


class StatesGroup(metaclass=StatesGroupMeta):
    """
    Base class for declaring groups of FSM states.

    Usage:
        class Registration(StatesGroup):
            waiting_for_name = State()
            waiting_for_phone = State()
    """

    @classmethod
    def get_all_states(cls) -> tuple[State, ...]:
        return getattr(cls, "_all_states", ())
