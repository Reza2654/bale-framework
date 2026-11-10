"""
Lightweight persistent SQLite storage for FSM without external dependencies.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from framework.fsm.key import StorageKey
from framework.fsm.state import State
from framework.fsm.storage.base import BaseStorage


class SqliteStorage(BaseStorage):
    """
    Zero-dependency persistent FSM storage backed by SQLite (WAL mode).

    Executes blocking database I/O asynchronously via `asyncio.to_thread`
    to ensure the main asyncio event loop is never blocked.
    """

    def __init__(self, db_path: str | Path = "fsm_storage.db") -> None:
        self.db_path = str(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS fsm_storage (
                        storage_key TEXT PRIMARY KEY,
                        state TEXT,
                        data TEXT NOT NULL DEFAULT '{}'
                    );
                    """
                )
        finally:
            conn.close()

    def _resolve_state(self, state: str | State | None) -> str | None:
        if isinstance(state, State):
            return state.state
        return state

    # ================= Synchronous worker functions =================

    def _set_state_sync(self, key_str: str, state_str: str | None) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO fsm_storage (storage_key, state, data)
                    VALUES (?, ?, '{}')
                    ON CONFLICT(storage_key) DO UPDATE SET state = excluded.state;
                    """,
                    (key_str, state_str),
                )
        finally:
            conn.close()

    def _get_state_sync(self, key_str: str) -> str | None:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT state FROM fsm_storage WHERE storage_key = ?;",
                (key_str,),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def _set_data_sync(self, key_str: str, data: dict[str, Any]) -> None:
        data_json = json.dumps(data)
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO fsm_storage (storage_key, state, data)
                    VALUES (?, NULL, ?)
                    ON CONFLICT(storage_key) DO UPDATE SET data = excluded.data;
                    """,
                    (key_str, data_json),
                )
        finally:
            conn.close()

    def _get_data_sync(self, key_str: str) -> dict[str, Any]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT data FROM fsm_storage WHERE storage_key = ?;",
                (key_str,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except Exception:
                    return {}
            return {}
        finally:
            conn.close()

    def _clear_sync(self, key_str: str) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    "DELETE FROM fsm_storage WHERE storage_key = ?;",
                    (key_str,),
                )
        finally:
            conn.close()

    # ================= Async BaseStorage interface =================

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        state_str = self._resolve_state(state)
        await asyncio.to_thread(self._set_state_sync, key.to_string(), state_str)

    async def get_state(self, key: StorageKey) -> str | None:
        return await asyncio.to_thread(self._get_state_sync, key.to_string())

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        await asyncio.to_thread(self._set_data_sync, key.to_string(), data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_data_sync, key.to_string())

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
        return current

    async def clear(self, key: StorageKey) -> None:
        await asyncio.to_thread(self._clear_sync, key.to_string())

    async def close(self) -> None:
        pass
