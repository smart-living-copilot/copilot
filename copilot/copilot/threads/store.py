"""Postgres-backed thread metadata store for sidebar chat summaries."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from copilot.core.database import get_connection_pool
from copilot.threads.models import DEFAULT_THREAD_TITLE, ThreadRecord


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _row_to_record(row: dict[str, Any]) -> ThreadRecord:
    return {
        "id": str(row["id"]),
        "title": str(row["title"]),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
    }


def init_thread_store() -> None:
    return None


def list_threads() -> list[ThreadRecord]:
    with get_connection_pool().connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM threads
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def get_thread(thread_id: str) -> ThreadRecord | None:
    with get_connection_pool().connection() as connection:
        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM threads
            WHERE id = %s
            """,
            (thread_id,),
        ).fetchone()
    return _row_to_record(row) if row is not None else None


def create_thread(
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

    with get_connection_pool().connection() as connection:
        row = connection.execute(
            """
            INSERT INTO threads(id, title, created_at, updated_at)
            VALUES(%s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            RETURNING id, title, created_at, updated_at
            """,
            (record_id, record_title, record_created_at, record_updated_at),
        ).fetchone()
        if row is None:
            row = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM threads
                WHERE id = %s
                """,
                (record_id,),
            ).fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError(f"Thread {record_id} could not be created")
    return _row_to_record(row)


def sync_thread_after_run(
    thread_id: str,
    *,
    suggested_title: str | None = None,
) -> ThreadRecord | None:
    now = _now_iso()
    next_title = suggested_title.strip()[:50] if isinstance(suggested_title, str) else None
    if next_title == "":
        next_title = None

    with get_connection_pool().connection() as connection:
        existing = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM threads
            WHERE id = %s
            """,
            (thread_id,),
        ).fetchone()
        if existing is None:
            return None

        current_title = str(existing["title"])
        resolved_title = (
            next_title if next_title and current_title == DEFAULT_THREAD_TITLE else current_title
        )
        row = connection.execute(
            """
            UPDATE threads
            SET title = %s, updated_at = %s
            WHERE id = %s
            RETURNING id, title, created_at, updated_at
            """,
            (resolved_title, now, thread_id),
        ).fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError(f"Thread {thread_id} could not be touched")
    return _row_to_record(row)


def touch_thread(thread_id: str) -> ThreadRecord | None:
    return sync_thread_after_run(thread_id)


def update_thread_title(
    *,
    thread_id: str,
    title: str,
    force: bool = False,
) -> ThreadRecord:
    next_title = title.strip()[:50]
    if not next_title:
        raise ValueError("Title is required")

    now = _now_iso()
    with get_connection_pool().connection() as connection:
        row = connection.execute(
            """
            INSERT INTO threads(id, title, created_at, updated_at)
            VALUES(%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET title = CASE
                    WHEN %s OR threads.title = %s THEN EXCLUDED.title
                    ELSE threads.title
                END,
                updated_at = CASE
                    WHEN %s OR threads.title = %s THEN EXCLUDED.updated_at
                    ELSE threads.updated_at
                END
            RETURNING id, title, created_at, updated_at
            """,
            (
                thread_id,
                next_title,
                now,
                now,
                force,
                DEFAULT_THREAD_TITLE,
                force,
                DEFAULT_THREAD_TITLE,
            ),
        ).fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError(f"Thread {thread_id} could not be updated")
    return _row_to_record(row)


def delete_thread(thread_id: str) -> bool:
    with get_connection_pool().connection() as connection:
        row = connection.execute(
            "DELETE FROM threads WHERE id = %s RETURNING id",
            (thread_id,),
        ).fetchone()
        connection.commit()
    return row is not None
