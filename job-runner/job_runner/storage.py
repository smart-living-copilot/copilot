from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import aiosqlite

from job_runner.models import CreateJobRequest, Job


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def iso_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def row_to_job(row: aiosqlite.Row) -> Job:
    return Job(
        id=row["id"],
        name=row["name"],
        thread_id=row["thread_id"],
        job_type=row["job_type"],
        prompt=row["prompt"],
        analysis_code=row["analysis_code"],
        enabled=bool(row["enabled"]),
        trigger_type=row["trigger_type"],
        run_at=iso_to_dt(row["run_at"]),
        interval_seconds=row["interval_seconds"],
        next_run_at=iso_to_dt(row["next_run_at"]),
        thing_id=row["thing_id"],
        event_name=row["event_name"],
        subscription_id=row["subscription_id"],
        subscription_input=json.loads(row["subscription_input_json"])
        if row["subscription_input_json"]
        else None,
        created_at=iso_to_dt(row["created_at"]) or utc_now(),
        updated_at=iso_to_dt(row["updated_at"]) or utc_now(),
        last_run_at=iso_to_dt(row["last_run_at"]),
        last_error=row["last_error"],
        last_response=row["last_response"],
        run_count=int(row["run_count"] or 0),
        last_fetch_value=row["last_fetch_value"],
    )


class JobRepository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    job_type TEXT NOT NULL DEFAULT 'prompt',
                    prompt TEXT,
                    analysis_code TEXT,
                    enabled INTEGER NOT NULL,
                    trigger_type TEXT NOT NULL,
                    run_at TEXT,
                    interval_seconds INTEGER,
                    next_run_at TEXT,
                    thing_id TEXT,
                    event_name TEXT,
                    subscription_id TEXT,
                    subscription_input_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_run_at TEXT,
                    last_error TEXT,
                    last_response TEXT,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    last_fetch_value TEXT
                )
                """
            )
            # Lightweight migration for older local DBs created before last_response existed.
            cursor = await db.execute("PRAGMA table_info(jobs)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "job_type" not in columns:
                await db.execute(
                    "ALTER TABLE jobs ADD COLUMN job_type TEXT NOT NULL DEFAULT 'prompt'"
                )
            if "analysis_code" not in columns:
                await db.execute("ALTER TABLE jobs ADD COLUMN analysis_code TEXT")
            if "last_response" not in columns:
                await db.execute("ALTER TABLE jobs ADD COLUMN last_response TEXT")
            if "run_count" not in columns:
                await db.execute("ALTER TABLE jobs ADD COLUMN run_count INTEGER NOT NULL DEFAULT 0")
            if "last_fetch_value" not in columns:
                await db.execute("ALTER TABLE jobs ADD COLUMN last_fetch_value TEXT")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_due ON jobs(trigger_type, enabled, next_run_at)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_subscription ON jobs(subscription_id, enabled)"
            )
            await db.commit()

    async def create_job(
        self,
        request: CreateJobRequest,
        *,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        now = utc_now()
        job_id = str(uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO jobs (
                    id, name, thread_id, job_type, prompt, analysis_code, enabled, trigger_type,
                    run_at, interval_seconds, next_run_at,
                    thing_id, event_name, subscription_id, subscription_input_json,
                    created_at, updated_at, last_run_at, last_error, last_response,
                    run_count, last_fetch_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    request.name,
                    request.thread_id,
                    request.job_type,
                    request.prompt or "",
                    request.analysis_code,
                    1,
                    request.trigger_type,
                    dt_to_iso(request.run_at),
                    request.interval_seconds,
                    dt_to_iso(next_run_at),
                    request.thing_id,
                    request.event_name,
                    subscription_id,
                    json.dumps(request.subscription_input)
                    if request.subscription_input is not None
                    else None,
                    dt_to_iso(now),
                    dt_to_iso(now),
                    None,
                    None,
                    None,
                    0,
                    None,
                ),
            )
            await db.commit()
        return await self.get_job(job_id)

    async def get_job(self, job_id: str) -> Job:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = await cursor.fetchone()
        if row is None:
            raise KeyError(job_id)
        return row_to_job(row)

    async def list_jobs(self, thread_id: str | None = None) -> list[Job]:
        query = "SELECT * FROM jobs"
        params: tuple[Any, ...] = ()
        if thread_id:
            query += " WHERE thread_id = ?"
            params = (thread_id,)
        query += " ORDER BY created_at DESC"

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [row_to_job(row) for row in rows]

    async def delete_job(self, job_id: str) -> Job:
        job = await self.get_job(job_id)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            await db.commit()
        return job

    async def list_due_time_jobs(self, *, now: datetime) -> list[Job]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM jobs
                WHERE trigger_type = 'time'
                  AND enabled = 1
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= ?
                ORDER BY next_run_at ASC
                """,
                (dt_to_iso(now),),
            )
            rows = await cursor.fetchall()
        return [row_to_job(row) for row in rows]

    async def list_event_jobs_for_subscription(self, subscription_id: str) -> list[Job]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM jobs
                WHERE trigger_type = 'event' AND enabled = 1 AND subscription_id = ?
                """,
                (subscription_id,),
            )
            rows = await cursor.fetchall()
        return [row_to_job(row) for row in rows]

    async def list_enabled_event_jobs(self) -> list[Job]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM jobs WHERE trigger_type = 'event' AND enabled = 1"
            )
            rows = await cursor.fetchall()
        return [row_to_job(row) for row in rows]

    async def set_subscription_id(self, job_id: str, subscription_id: str | None) -> None:
        now = utc_now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE jobs SET subscription_id = ?, updated_at = ? WHERE id = ?",
                (subscription_id, dt_to_iso(now), job_id),
            )
            await db.commit()

    async def mark_time_job_result(
        self,
        *,
        job: Job,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None = None,
    ) -> None:
        next_run_at: datetime | None
        enabled = job.enabled

        if job.interval_seconds:
            next_run_at = now + timedelta(seconds=job.interval_seconds)
        else:
            next_run_at = None
            enabled = False

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE jobs
                SET next_run_at = ?,
                    enabled = ?,
                    last_run_at = ?,
                    last_error = ?,
                    last_response = ?,
                    run_count = run_count + 1,
                    last_fetch_value = CASE WHEN ? IS NULL THEN last_fetch_value ELSE ? END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    dt_to_iso(next_run_at),
                    1 if enabled else 0,
                    dt_to_iso(now),
                    None if success else error,
                    response_text if success else None,
                    last_fetch_value,
                    last_fetch_value,
                    dt_to_iso(now),
                    job.id,
                ),
            )
            await db.commit()

    async def mark_event_job_result(
        self,
        *,
        job_id: str,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None = None,
    ) -> None:
        await self._mark_job_result(
            job_id=job_id,
            now=now,
            success=success,
            error=error,
            response_text=response_text,
            last_fetch_value=last_fetch_value,
        )

    async def mark_manual_job_result(
        self,
        *,
        job_id: str,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None = None,
    ) -> None:
        await self._mark_job_result(
            job_id=job_id,
            now=now,
            success=success,
            error=error,
            response_text=response_text,
            last_fetch_value=last_fetch_value,
        )

    async def _mark_job_result(
        self,
        *,
        job_id: str,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE jobs
                SET last_run_at = ?,
                    last_error = ?,
                    last_response = ?,
                    run_count = run_count + 1,
                    last_fetch_value = CASE WHEN ? IS NULL THEN last_fetch_value ELSE ? END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    dt_to_iso(now),
                    None if success else error,
                    response_text if success else None,
                    last_fetch_value,
                    last_fetch_value,
                    dt_to_iso(now),
                    job_id,
                ),
            )
            await db.commit()
