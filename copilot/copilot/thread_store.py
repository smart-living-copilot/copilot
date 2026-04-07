"""SQLite-backed thread metadata store for sidebar chat summaries."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import TypedDict

DEFAULT_THREAD_TITLE = "New Chat"


class ThreadRecord(TypedDict):
    id: str
    title: str
    createdAt: str
    updatedAt: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS threads (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL DEFAULT 'New Chat',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_threads_updated_at
          ON threads(updated_at DESC, created_at DESC);
        """
    )


def _row_to_record(row: sqlite3.Row) -> ThreadRecord:
    return {
        "id": str(row["id"]),
        "title": str(row["title"]),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
    }


def init_thread_store(db_path: str) -> None:
    with _connect(db_path):
        pass


def list_threads(db_path: str) -> list[ThreadRecord]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM threads
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()

    return [_row_to_record(row) for row in rows]


def get_thread(db_path: str, thread_id: str) -> ThreadRecord | None:
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM threads
            WHERE id = ?
            """,
            (thread_id,),
        ).fetchone()

    return _row_to_record(row) if row is not None else None


def create_thread(
    db_path: str,
    *,
    thread_id: str | None = None,
    title: str = DEFAULT_THREAD_TITLE,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> ThreadRecord:
    now = _now_iso()
    record_id = thread_id or str(uuid.uuid4())
    record_created_at = created_at or now
    record_updated_at = updated_at or record_created_at
    record_title = title.strip()[:50] or DEFAULT_THREAD_TITLE

    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO threads(id, title, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (record_id, record_title, record_created_at, record_updated_at),
        )
        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM threads
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()

    if row is None:
        raise RuntimeError(f"Thread {record_id} could not be created")

    return _row_to_record(row)


def sync_thread_after_run(
    db_path: str,
    thread_id: str,
    *,
    suggested_title: str | None = None,
) -> ThreadRecord | None:
    now = _now_iso()
    next_title = suggested_title.strip()[:50] if isinstance(suggested_title, str) else None
    if next_title == "":
        next_title = None

    with _connect(db_path) as connection:
        existing = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM threads
            WHERE id = ?
            """,
            (thread_id,),
        ).fetchone()
        if existing is None:
            return None

        current_title = str(existing["title"])
        resolved_title = (
            next_title if next_title and current_title == DEFAULT_THREAD_TITLE else current_title
        )
        connection.execute(
            """
            UPDATE threads
            SET title = ?, updated_at = ?
            WHERE id = ?
            """,
            (resolved_title, now, thread_id),
        )
        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM threads
            WHERE id = ?
            """,
            (thread_id,),
        ).fetchone()

    if row is None:
        raise RuntimeError(f"Thread {thread_id} could not be touched")

    return _row_to_record(row)


def touch_thread(db_path: str, thread_id: str) -> ThreadRecord | None:
    return sync_thread_after_run(db_path, thread_id)


def update_thread_title(
    db_path: str,
    *,
    thread_id: str,
    title: str,
    force: bool = False,
) -> ThreadRecord:
    next_title = title.strip()[:50]
    if not next_title:
        raise ValueError("Title is required")

    now = _now_iso()
    with _connect(db_path) as connection:
        existing = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM threads
            WHERE id = ?
            """,
            (thread_id,),
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO threads(id, title, created_at, updated_at)
                VALUES(?, ?, ?, ?)
                """,
                (thread_id, next_title, now, now),
            )
        else:
            current_title = str(existing["title"])
            resolved_title = (
                next_title if force or current_title == DEFAULT_THREAD_TITLE else current_title
            )
            if resolved_title != current_title:
                connection.execute(
                    """
                    UPDATE threads
                    SET title = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (resolved_title, now, thread_id),
                )

        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM threads
            WHERE id = ?
            """,
            (thread_id,),
        ).fetchone()

    if row is None:
        raise RuntimeError(f"Thread {thread_id} could not be updated")

    return _row_to_record(row)


def delete_thread(db_path: str, thread_id: str) -> bool:
    with _connect(db_path) as connection:
        cursor = connection.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
        return cursor.rowcount > 0
