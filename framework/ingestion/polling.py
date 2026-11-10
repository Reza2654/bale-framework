"""
Robust, non-blocking Long-Polling ingestion engine for the Bale Bot platform.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from framework.client.client import BaleBotClient
from framework.client.exceptions import BaleConflictError, BaleNetworkError
from framework.ingestion.base import BaseIngestionEngine, UpdateConsumer

logger = logging.getLogger("bale.ingestion.polling")


class LongPollingEngine(BaseIngestionEngine):
    """
    High-performance Long-Polling engine.

    Architecture:
    - Dedicated Fetcher coroutine: Polls Bale's getUpdates in a loop and feeds a bounded queue.
    - Worker Pool coroutines: Pluggable pool of workers pulling updates from the queue and
      invoking the downstream consumer/dispatcher concurrently.
    - Backpressure: If workers cannot keep up, the queue fills and the fetcher pauses getUpdates.
    - Resiliency: Automatic reconnect with exponential backoff on network drops or 5xx gateway errors.
    - Cross-platform signal handling: Cleanly catches SIGINT and SIGTERM on Linux, macOS, and Windows.
    """

    def __init__(
        self,
        client: BaleBotClient,
        consumer: UpdateConsumer,
        allowed_updates: list[str] | None = None,
        limit: int = 100,
        poll_timeout: int = 20,
        drop_pending_updates: bool = False,
        workers_count: int = 16,
        queue_max_size: int = 1000,
        shutdown_drain_timeout: float = 10.0,
    ) -> None:
        super().__init__(client=client, consumer=consumer)
        self.allowed_updates = allowed_updates
        self.limit = limit
        self.poll_timeout = poll_timeout
        self.drop_pending_updates = drop_pending_updates
        self.workers_count = max(1, workers_count)
        self.queue_max_size = queue_max_size
        self.shutdown_drain_timeout = shutdown_drain_timeout

        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.queue_max_size)
        self._offset: int | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._fetcher_task: asyncio.Task[None] | None = None
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._signals_registered: bool = False

    async def start(self) -> None:
        """Start the fetcher and worker pool tasks."""
        if self._is_running:
            logger.warning("LongPollingEngine is already running.")
            return

        logger.info("Initializing LongPollingEngine (workers: %d)...", self.workers_count)

        if self.drop_pending_updates:
            logger.info("Dropping pending updates from Bale queue...")
            try:
                await self.client.delete_webhook(drop_pending_updates=True)
            except Exception as e:
                logger.warning("Could not drop pending updates via deleteWebhook: %s", e)

        self._stop_event.clear()
        self._is_running = True

        # Spawn worker tasks
        for worker_id in range(self.workers_count):
            task = asyncio.create_task(
                self._worker_loop(worker_id),
                name=f"bale-poll-worker-{worker_id}",
            )
            self._worker_tasks.append(task)

        # Spawn fetcher task
        self._fetcher_task = asyncio.create_task(
            self._fetcher_loop(),
            name="bale-poll-fetcher",
        )
        logger.info("LongPollingEngine successfully started.")

    async def stop(self) -> None:
        """Gracefully stop polling and drain pending updates."""
        if not self._is_running:
            return

        logger.info("Shutting down LongPollingEngine...")
        self._is_running = False
        self._stop_event.set()

        # 1. Cancel the fetcher to stop receiving new updates
        if self._fetcher_task and not self._fetcher_task.done():
            self._fetcher_task.cancel()
            try:
                await self._fetcher_task
            except asyncio.CancelledError:
                pass

        # 2. Drain the queue with a timeout
        pending_items = self._queue.qsize()
        if pending_items > 0:
            logger.info(
                "Draining %d pending updates from queue (timeout: %.1fs)...",
                pending_items,
                self.shutdown_drain_timeout,
            )
            try:
                await asyncio.wait_for(self._queue.join(), timeout=self.shutdown_drain_timeout)
                logger.info("All pending updates successfully processed.")
            except asyncio.TimeoutError:
                logger.warning(
                    "Timed out waiting for update queue to drain. %d items abandoned.",
                    self._queue.qsize(),
                )

        # 3. Cancel worker tasks
        for task in self._worker_tasks:
            if not task.done():
                task.cancel()

        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            self._worker_tasks.clear()

        logger.info("LongPollingEngine shutdown complete.")

    async def run_until_stopped(self) -> None:
        """Run the polling loop and attach OS signal listeners until interrupted."""
        self._register_signal_handlers()
        await self.start()
        try:
            await self._stop_event.wait()
        finally:
            await self.stop()

    def _register_signal_handlers(self) -> None:
        """Set up cross-platform signal handlers for SIGINT and SIGTERM."""
        if self._signals_registered:
            return

        loop = asyncio.get_running_loop()

        def _handle_signal(sig_name: str) -> None:
            logger.info("Received termination signal %s. Initiating graceful shutdown...", sig_name)
            self._stop_event.set()

        # Unix / POSIX
        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, _handle_signal, sig.name)
                except (NotImplementedError, RuntimeError):
                    pass
        else:
            # Windows fallback: Python on Windows cannot use loop.add_signal_handler with ProactorEventLoop
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    signal.signal(
                        sig,
                        lambda s, f: loop.call_soon_threadsafe(
                            _handle_signal,
                            signal.Signals(s).name,
                        ),
                    )
                except (ValueError, OSError):
                    pass

        self._signals_registered = True

    async def _fetcher_loop(self) -> None:
        """Dedicated coroutine to continuously pull updates from Bale."""
        consecutive_errors = 0

        while not self._stop_event.is_set():
            try:
                updates = await self.client.get_updates(
                    offset=self._offset,
                    limit=self.limit,
                    timeout=self.poll_timeout,
                    allowed_updates=self.allowed_updates,
                )
                consecutive_errors = 0

                for update in updates:
                    update_id = update.get("update_id")
                    if update_id is not None:
                        self._offset = update_id + 1

                    # Push to queue (blocks if queue is full, enforcing backpressure)
                    await self._queue.put(update)

            except asyncio.CancelledError:
                break
            except BaleConflictError as conflict_err:
                logger.critical(
                    "Conflict detected: another instance is already polling or webhook is active: %s",
                    conflict_err,
                )
                self._stop_event.set()
                break
            except (BaleNetworkError, Exception) as exc:
                consecutive_errors += 1
                backoff = min(30.0, (1.5 ** min(consecutive_errors, 8)))
                logger.error(
                    "Error during getUpdates (failure #%d): %s. Backing off for %.1fs...",
                    consecutive_errors,
                    exc,
                    backoff,
                )
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    break

    async def _worker_loop(self, worker_id: int) -> None:
        """Worker task processing updates from the queue."""
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                update = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self.consumer(update)
            except Exception as exc:
                logger.exception(
                    "Unhandled exception in worker #%d while dispatching update %s: %s",
                    worker_id,
                    update.get("update_id"),
                    exc,
                )
            finally:
                self._queue.task_done()
