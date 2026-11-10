"""Handler registration, filter evaluation, and dependency injection."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from framework.context.context import BaleContext
from framework.routing.filters.base import BaseFilter


class HandlerRecord:
    """
    Wraps a target handler function along with its assigned filters.
    Performs signature inspection to dynamically inject accepted arguments.
    """

    def __init__(
        self,
        callback: Callable[..., Awaitable[Any]],
        filters: list[BaseFilter | Callable[[BaleContext], Awaitable[bool]]],
    ) -> None:
        self.callback = callback
        self.filters = filters
        self._signature = inspect.signature(callback)
        self._accepts_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in self._signature.parameters.values()
        )
        self._param_names = set(self._signature.parameters.keys())

    async def check(self, ctx: BaleContext) -> tuple[bool, dict[str, Any]]:
        """
        Evaluate all attached filters sequentially.

        Returns (True, merged_filter_data) if ALL filters pass, else (False, {}).
        """
        merged_data: dict[str, Any] = {}

        for f in self.filters:
            if isinstance(f, BaseFilter):
                result = await f(ctx)
            else:
                result = await f(ctx)  # type: ignore[misc]

            if result is False or result is None:
                return False, {}

            if isinstance(result, dict):
                merged_data.update(result)

        return True, merged_data

    async def call(self, ctx: BaleContext, data: dict[str, Any]) -> Any:
        """
        Prepare arguments and invoke the callback according to its parameter signature.
        """
        resolved_kwargs: dict[str, Any] = {}

        # Merge base context data and filter outputs
        available_data = dict(ctx.data)
        available_data.update(data)

        # Standard injection candidates
        available_data["ctx"] = ctx
        available_data["event"] = ctx
        if "state" in ctx.data:
            available_data["state"] = ctx.data["state"]

        for param_name, param in self._signature.parameters.items():
            if param_name in available_data:
                resolved_kwargs[param_name] = available_data[param_name]
            elif (
                param.default is inspect.Parameter.empty
                and param.kind
                not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            ):
                # If first parameter has no default and hasn't been matched, pass ctx
                if param_name in ("ctx", "event") or list(self._signature.parameters.keys())[0] == param_name:
                    resolved_kwargs[param_name] = ctx

        if self._accepts_kwargs:
            for k, v in available_data.items():
                if k not in resolved_kwargs:
                    resolved_kwargs[k] = v

        return await self.callback(**resolved_kwargs)

    def __repr__(self) -> str:
        return f"HandlerRecord(callback={self.callback.__name__}, filters={len(self.filters)})"
