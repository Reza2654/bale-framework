"""Safe fire-and-forget background task executor with graceful shutdown drain."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, Callable

logger = logging.getLogger("bale.tasks.executor")

TaskErrorHandler = Callable[[asyncio.Task[Any], Exception], None]


class TaskExecutor:
    """
    Manages non-blocking background task execution.

    Features:
    - Strong reference tracking prevents garbage collection of running asyncio tasks.
    - Automatic error logging on task completion prevents unhandled task exceptions.
    - Graceful shutdown awaits in-flight background operations with a configurable timeout.
    """

    def __init__(self, on_error: TaskErrorHandler | None = None) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._on_error = on_error
        self._is_shutting_down = False

    @property
    def active_count(self) -> int:
        """Returns the number of currently executing background tasks."""
        return len(self._tasks)

    def spawn(
        self,
        coro: Coroutine[Any, Any, Any],
        name: str | None = None,
    ) -> asyncio.Task[Any]:
        """
        Spawn an asynchronous coroutine as a tracked background task.

        :param coro: The coroutine to execute.
        :param name: Optional human-readable name for logging and telemetry.
        :return: The created asyncio.Task.
        """
        if self._is_shutting_down:
            raise RuntimeError("Cannot spawn tasks: TaskExecutor is shutting down.")

        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task[Any]) -> None:
        """Callback invoked immediately when a spawned task completes."""
        self._tasks.discard(task)

        if task.cancelled():
            logger.debug("Background task %s was cancelled.", task.get_name())
            return

        exc = task.exception()
        if exc is not None:
            logger.error(
                "Background task %s raised unhandled exception: %s",
                task.get_name(),
                exc,
                exc_info=exc,
            )
            if self._on_error is not None:
                try:
                    self._on_error(task, exc)
                except Exception as hook_err:
                    logger.error("Error in TaskExecutor on_error hook: %s", hook_err)

    async def shutdown(self, timeout: float = 10.0) -> None:
        """
        Gracefully drain all active background tasks within the specified timeout.
        Cancels remaining tasks if the timeout is exceeded.
        """
        self._is_shutting_down = True
        if not self._tasks:
            return

        logger.info("Draining %d active background tasks (timeout: %.1fs)...", len(self._tasks), timeout)

        # Wait for completion of running tasks
        pending_tasks = set(self._tasks)
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending_tasks, return_exceptions=True),
                timeout=timeout,
            )
            logger.info("All background tasks completed successfully.")
        except asyncio.TimeoutError:
            logger.warning(
                "Timeout reached while draining tasks. Cancelling %d remaining tasks...",
                len(self._tasks),
            )
            for t in list(self._tasks):
                if not t.done():
                    t.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
