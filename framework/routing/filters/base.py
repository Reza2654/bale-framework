"""Abstract base filter for routing matching."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from framework.context.context import BaleContext


class BaseFilter(ABC):
    """
    Abstract predicate evaluated against an incoming BaleContext.

    Return values:
    - `True`: Filter matches. Handler proceeds with existing arguments.
    - `False`: Filter does not match. Router tries the next handler.
    - `dict[str, Any]`: Filter matches and passes extracted keyword arguments
      (e.g., CommandObject or unpacked CallbackData) directly to the handler function.
    """

    @abstractmethod
    async def __call__(self, event: BaleContext) -> bool | dict[str, Any]:
        """Evaluate the filter against the event context."""
        raise NotImplementedError
