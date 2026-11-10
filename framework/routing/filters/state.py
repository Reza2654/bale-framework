"""FSM State filter for matching active state in conversation context."""

from __future__ import annotations

from typing import Any

from framework.context.context import BaleContext
from framework.fsm.context import FSMContext
from framework.fsm.state import State, StatesGroup
from framework.routing.filters.base import BaseFilter


class StateFilter(BaseFilter):
    """
    Matches the active FSM state of the user.

    Usage:
        @router.message(StateFilter(None))                    # Only when no state is set
        @router.message(StateFilter("*"))                     # Any state
        @router.message(StateFilter(Registration.name))       # Specific state
        @router.message(StateFilter(Registration))            # Any state within Registration group
    """

    def __init__(self, *states: str | State | type[StatesGroup] | None) -> None:
        self.states = states

    async def __call__(self, event: BaleContext) -> bool:
        state_ctx: FSMContext | None = event.data.get("state")
        if state_ctx is None:
            active_state = None
        else:
            active_state = await state_ctx.get_state()

        for target in self.states:
            # Wildcard matches everything
            if target == "*":
                return True

            # Match None / empty state
            if target is None:
                if active_state is None:
                    return True
                continue

            # Match entire StatesGroup
            if isinstance(target, type) and issubclass(target, StatesGroup):
                if active_state in target:
                    return True
                continue

            # Match State instance
            if isinstance(target, State):
                if active_state == target.state:
                    return True
                continue

            # Match raw string
            if isinstance(target, str):
                if active_state == target:
                    return True

        return False
