"""Persistent SQLite database for the Uptime & Health Monitor Bot."""
from __future__ import annotations
import asyncio
from datetime import datetime
import logging
from pathlib import Path
import sqlite3
from typing import Any
from app.domain.models import CheckResult, MonitoredURL, User

logger = logging.getLogger("bale.monitor.db")

class MonitorDatabase:
    def __init__(self, db_path: str | Path = "data/monitor.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db_sync()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db_sync(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                plan_name TEXT NOT NULL DEFAULT 'base',
                notify_chat_id TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS monitored_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                alias TEXT NOT NULL DEFAULT '',
                last_status_code INTEGER,
                last_response_time_ms REAL,
                last_checked_at TEXT,
                is_up INTEGER NOT NULL DEFAULT 1,
                failure_reason TEXT,
                downtime_started_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS downtime_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                status_code INTEGER,
                failure_reason TEXT,
                started_at TEXT NOT NULL,
                resolved_at TEXT,
                duration_seconds INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_urls_user ON monitored_urls(user_id);
            CREATE INDEX IF NOT EXISTS idx_urls_active ON monitored_urls(is_active);
            """)

    # ------------------ User Operations ------------------

    async def get_or_create_user(self, user_id: int, chat_id: int | str | None = None) -> User:
        return await asyncio.to_thread(self._get_or_create_user_sync, user_id, chat_id)

    def _get_or_create_user_sync(self, user_id: int, chat_id: int | str | None = None) -> User:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                if chat_id and str(row["notify_chat_id"]) != str(chat_id):
                    conn.execute("UPDATE users SET notify_chat_id = ? WHERE user_id = ?", (str(chat_id), user_id))
                return User(
                    user_id=row["user_id"],
                    plan_name=row["plan_name"],
                    notify_chat_id=str(chat_id or row["notify_chat_id"]),
                    is_active=bool(row["is_active"]),
                    created_at=row["created_at"],
                )

            now_str = datetime.now().isoformat()
            notify_id_str = str(chat_id) if chat_id else str(user_id)
            conn.execute(
                "INSERT INTO users (user_id, plan_name, notify_chat_id, is_active, created_at) VALUES (?, 'base', ?, 1, ?)",
                (user_id, notify_id_str, now_str),
            )
            return User(
                user_id=user_id,
                plan_name="base",
                notify_chat_id=notify_id_str,
                is_active=True,
                created_at=now_str,
            )

    async def set_user_plan(self, user_id: int, plan_name: str) -> bool:
        return await asyncio.to_thread(self._set_user_plan_sync, user_id, plan_name)

    def _set_user_plan_sync(self, user_id: int, plan_name: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("UPDATE users SET plan_name = ? WHERE user_id = ?", (plan_name, user_id))
            return cursor.rowcount > 0

    # ------------------ URL Operations ------------------

    async def get_user_urls(self, user_id: int) -> list[MonitoredURL]:
        return await asyncio.to_thread(self._get_user_urls_sync, user_id)

    def _get_user_urls_sync(self, user_id: int) -> list[MonitoredURL]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM monitored_urls WHERE user_id = ? AND is_active = 1 ORDER BY id ASC",
                (user_id,),
            ).fetchall()
            return [self._row_to_url(r) for r in rows]

    async def add_url(self, user_id: int, url: str, alias: str = "") -> MonitoredURL:
        return await asyncio.to_thread(self._add_url_sync, user_id, url, alias)

    def _add_url_sync(self, user_id: int, url: str, alias: str = "") -> MonitoredURL:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO monitored_urls (user_id, url, alias, is_up, is_active) VALUES (?, ?, ?, 1, 1)",
                (user_id, url, alias),
            )
            url_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM monitored_urls WHERE id = ?", (url_id,)).fetchone()
            return self._row_to_url(row)

    async def delete_url(self, url_id: int, user_id: int) -> bool:
        return await asyncio.to_thread(self._delete_url_sync, url_id, user_id)

    def _delete_url_sync(self, url_id: int, user_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE monitored_urls SET is_active = 0 WHERE id = ? AND user_id = ?",
                (url_id, user_id),
            )
            return cursor.rowcount > 0

    async def get_all_active_targets(self) -> list[tuple[MonitoredURL, User]]:
        return await asyncio.to_thread(self._get_all_active_targets_sync)

    def _get_all_active_targets_sync(self) -> list[tuple[MonitoredURL, User]]:
        with self._get_connection() as conn:
            query = """
            SELECT 
                u.id as url_id, u.user_id, u.url, u.alias, u.last_status_code, 
                u.last_response_time_ms, u.last_checked_at, u.is_up, u.failure_reason, 
                u.downtime_started_at, u.is_active,
                usr.plan_name, usr.notify_chat_id, usr.is_active as user_active, usr.created_at as user_created
            FROM monitored_urls u
            JOIN users usr ON u.user_id = usr.user_id
            WHERE u.is_active = 1 AND usr.is_active = 1
            """
            rows = conn.execute(query).fetchall()
            results = []
            for r in rows:
                url_obj = MonitoredURL(
                    id=r["url_id"],
                    user_id=r["user_id"],
                    url=r["url"],
                    alias=r["alias"],
                    last_status_code=r["last_status_code"],
                    last_response_time_ms=r["last_response_time_ms"],
                    last_checked_at=r["last_checked_at"],
                    is_up=bool(r["is_up"]),
                    failure_reason=r["failure_reason"],
                    downtime_started_at=r["downtime_started_at"],
                    is_active=bool(r["is_active"]),
                )
                user_obj = User(
                    user_id=r["user_id"],
                    plan_name=r["plan_name"],
                    notify_chat_id=r["notify_chat_id"],
                    is_active=bool(r["user_active"]),
                    created_at=r["user_created"],
                )
                results.append((url_obj, user_obj))
            return results

    async def update_check_result(
        self,
        url_id: int,
        check: CheckResult,
        now_iso: str,
        was_up: bool,
    ) -> int | None:
        """
        Updates the URL record with the check result.
        If recovered from downtime, logs the resolved event and returns the downtime duration in seconds.
        """
        return await asyncio.to_thread(self._update_check_result_sync, url_id, check, now_iso, was_up)

    def _update_check_result_sync(
        self,
        url_id: int,
        check: CheckResult,
        now_iso: str,
        was_up: bool,
    ) -> int | None:
        duration_seconds: int | None = None
        with self._get_connection() as conn:
            # Case 1: Was DOWN and now recovered (UP)
            if not was_up and check.is_up:
                row = conn.execute("SELECT downtime_started_at, user_id, url FROM monitored_urls WHERE id = ?", (url_id,)).fetchone()
                if row and row["downtime_started_at"]:
                    try:
                        start_dt = datetime.fromisoformat(row["downtime_started_at"])
                        now_dt = datetime.fromisoformat(now_iso)
                        duration_seconds = max(1, int((now_dt - start_dt).total_seconds()))
                    except Exception:
                        duration_seconds = 60

                    # Update downtime log
                    conn.execute(
                        """
                        UPDATE downtime_logs 
                        SET resolved_at = ?, duration_seconds = ?
                        WHERE url_id = ? AND resolved_at IS NULL
                        """,
                        (now_iso, duration_seconds, url_id),
                    )

                conn.execute(
                    """
                    UPDATE monitored_urls 
                    SET last_status_code = ?, last_response_time_ms = ?, last_checked_at = ?,
                        is_up = 1, failure_reason = NULL, downtime_started_at = NULL
                    WHERE id = ?
                    """,
                    (check.status_code, check.response_time_ms, now_iso, url_id),
                )

            # Case 2: Was UP and now DOWN
            elif was_up and not check.is_up:
                row = conn.execute("SELECT user_id, url FROM monitored_urls WHERE id = ?", (url_id,)).fetchone()
                if row:
                    conn.execute(
                        """
                        INSERT INTO downtime_logs (url_id, user_id, url, status_code, failure_reason, started_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (url_id, row["user_id"], row["url"], check.status_code, check.failure_reason, now_iso),
                    )
                conn.execute(
                    """
                    UPDATE monitored_urls 
                    SET last_status_code = ?, last_response_time_ms = ?, last_checked_at = ?,
                        is_up = 0, failure_reason = ?, downtime_started_at = ?
                    WHERE id = ?
                    """,
                    (check.status_code, check.response_time_ms, now_iso, check.failure_reason, now_iso, url_id),
                )

            # Case 3: State didn't change (still UP or still DOWN)
            else:
                conn.execute(
                    """
                    UPDATE monitored_urls 
                    SET last_status_code = ?, last_response_time_ms = ?, last_checked_at = ?
                    WHERE id = ?
                    """,
                    (check.status_code, check.response_time_ms, now_iso, url_id),
                )

        return duration_seconds

    @staticmethod
    def _row_to_url(row: sqlite3.Row) -> MonitoredURL:
        return MonitoredURL(
            id=row["id"],
            user_id=row["user_id"],
            url=row["url"],
            alias=row["alias"],
            last_status_code=row["last_status_code"],
            last_response_time_ms=row["last_response_time_ms"],
            last_checked_at=row["last_checked_at"],
            is_up=bool(row["is_up"]),
            failure_reason=row["failure_reason"],
            downtime_started_at=row["downtime_started_at"],
            is_active=bool(row["is_active"]),
        )
