"""Lightweight async interval scheduler for recurring background bot jobs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("bale.tasks.scheduler")

ScheduledJobCallable = Callable[[], Awaitable[Any]]


@dataclass(slots=True)
class ScheduledJob:
    """Descriptor for a registered recurring job."""

    name: str
    interval_seconds: float
    callback: ScheduledJobCallable
    run_immediately: bool = False


class IntervalScheduler:
    """
    Lightweight, in-process periodic job scheduler.

    Ideal for:
    - Periodic cache/FSM cleanup routines
    - Heartbeat / health check pings
    - Scheduled broadcasts and notification digests
    """

    def __init__(self) -> None:
        self._jobs: list[ScheduledJob] = []
        self._running_tasks: list[asyncio.Task[None]] = []
        self._stop_event: asyncio.Event = asyncio.Event()
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def add_job(
        self,
        name: str,
        interval_seconds: float,
        callback: ScheduledJobCallable,
        run_immediately: bool = False,
    ) -> None:
        """Register a new periodic job."""
        if interval_seconds <= 0:
            raise ValueError(f"Interval must be greater than zero, got {interval_seconds}")

        self._jobs.append(
            ScheduledJob(
                name=name,
                interval_seconds=interval_seconds,
                callback=callback,
                run_immediately=run_immediately,
            )
        )
        logger.debug("Scheduled job %r registered with interval %.1fs", name, interval_seconds)

    def start(self) -> None:
        """Start execution of all registered scheduled jobs in background tasks."""
        if self._is_running:
            logger.warning("IntervalScheduler is already running.")
            return

        self._stop_event.clear()
        self._is_running = True

        for job in self._jobs:
            task = asyncio.create_task(
                self._run_job_loop(job),
                name=f"bale-scheduler-job-{job.name}",
            )
            self._running_tasks.append(task)

        logger.info("IntervalScheduler started with %d registered jobs.", len(self._jobs))

    async def stop(self) -> None:
        """Stop all scheduled jobs and wait for running iterations to terminate."""
        if not self._is_running:
            return

        logger.info("Stopping IntervalScheduler...")
        self._is_running = False
        self._stop_event.set()

        for task in self._running_tasks:
            if not task.done():
                task.cancel()

        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
            self._running_tasks.clear()

        logger.info("IntervalScheduler stopped.")

    async def _run_job_loop(self, job: ScheduledJob) -> None:
        """Dedicated runner loop for an individual job."""
        if not job.run_immediately:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=job.interval_seconds)
                return
            except asyncio.TimeoutError:
                pass

        while not self._stop_event.is_set():
            try:
                logger.debug("Executing scheduled job %r...", job.name)
                await job.callback()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Scheduled job %r failed with unhandled exception: %s", job.name, exc)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=job.interval_seconds)
                break
            except asyncio.TimeoutError:
                continue
