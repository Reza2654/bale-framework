"""Abstract base contract for update ingestion engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from framework.client.client import BaleBotClient

# An UpdateConsumer is any callable that receives a raw update dict and processes it
UpdateConsumer = Callable[[dict[str, Any]], Awaitable[Any]]


class BaseIngestionEngine(ABC):
    """
    Abstract Port for incoming Update Ingestion.

    Decouples the source of incoming updates (Long-Polling or Webhook)
    from the downstream Dispatcher and Middleware pipelines.
    """

    def __init__(
        self,
        client: BaleBotClient,
        consumer: UpdateConsumer,
    ) -> None:
        self.client = client
        self.consumer = consumer
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        """Indicates whether the ingestion loop is actively running."""
        return self._is_running

    @abstractmethod
    async def start(self) -> None:
        """Start ingesting updates in non-blocking background tasks."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """Stop ingestion and wait for in-flight tasks to terminate cleanly."""
        raise NotImplementedError

    @abstractmethod
    async def run_until_stopped(self) -> None:
        """Block until an OS termination signal or explicit stop request occurs."""
        raise NotImplementedError
