from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from psycopg_pool import ConnectionPool

from copilot.core.database import DatabaseConnection, get_connection_pool
from copilot.jobs.models import CreateJobRequest, Job

_JOB_COLUMNS = """
    id, name, thread_id, job_type, prompt, analysis_code, enabled, trigger_type,
    run_at, interval_seconds, next_run_at, thing_id, event_name, subscription_id,
    subscription_input_json, created_at, updated_at, last_run_at, last_error,
    last_response, run_count, last_fetch_value
"""


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


def record_to_job(record: dict[str, Any]) -> Job:
    return Job(
        id=str(record["id"]),
        name=str(record["name"]),
        thread_id=str(record["thread_id"]),
        job_type=record["job_type"],
        prompt=record["prompt"],
        analysis_code=record["analysis_code"],
        enabled=bool(record["enabled"]),
        trigger_type=record["trigger_type"],
        run_at=iso_to_dt(record["run_at"]),
        interval_seconds=record["interval_seconds"],
        next_run_at=iso_to_dt(record["next_run_at"]),
        thing_id=record["thing_id"],
        event_name=record["event_name"],
        subscription_id=record["subscription_id"],
        subscription_input=json.loads(record["subscription_input_json"])
        if record["subscription_input_json"]
        else None,
        created_at=iso_to_dt(record["created_at"]) or utc_now(),
        updated_at=iso_to_dt(record["updated_at"]) or utc_now(),
        last_run_at=iso_to_dt(record["last_run_at"]),
        last_error=record["last_error"],
        last_response=record["last_response"],
        run_count=int(record["run_count"] or 0),
        last_fetch_value=record["last_fetch_value"],
    )


class JobRepository:
    def __init__(
        self,
        connection_pool: ConnectionPool[DatabaseConnection] | None = None,
    ) -> None:
        self._connection_pool = connection_pool or get_connection_pool()

    async def init(self) -> None:
        return None

    async def create_job(
        self,
        request: CreateJobRequest,
        *,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        return await asyncio.to_thread(
            self._create_job_sync,
            request,
            next_run_at,
            subscription_id,
        )

    def _create_job_sync(
        self,
        request: CreateJobRequest,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        now = utc_now()
        with self._connection_pool.connection() as connection:
            row = connection.execute(
                f"""
                INSERT INTO jobs (
                    id, name, thread_id, job_type, prompt, analysis_code, enabled,
                    trigger_type, run_at, interval_seconds, next_run_at, thing_id,
                    event_name, subscription_id, subscription_input_json, created_at,
                    updated_at, run_count
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, true,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, 0
                )
                RETURNING {_JOB_COLUMNS}
                """,
                (
                    str(uuid4()),
                    request.name,
                    request.thread_id,
                    request.job_type,
                    request.prompt or "",
                    request.analysis_code,
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
                ),
            ).fetchone()
            connection.commit()
        if row is None:
            raise RuntimeError("Job row was not returned")
        return record_to_job(row)

    async def get_job(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._get_job_sync, job_id)

    def _get_job_sync(self, job_id: str) -> Job:
        with self._connection_pool.connection() as connection:
            row = connection.execute(
                f"SELECT {_JOB_COLUMNS} FROM jobs WHERE id = %s",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return record_to_job(row)

    async def list_jobs(self, thread_id: str | None = None) -> list[Job]:
        return await asyncio.to_thread(self._list_jobs_sync, thread_id)

    def _list_jobs_sync(self, thread_id: str | None = None) -> list[Job]:
        with self._connection_pool.connection() as connection:
            if thread_id:
                rows = connection.execute(
                    f"""
                    SELECT {_JOB_COLUMNS}
                    FROM jobs
                    WHERE thread_id = %s
                    ORDER BY created_at DESC
                    """,
                    (thread_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"SELECT {_JOB_COLUMNS} FROM jobs ORDER BY created_at DESC"
                ).fetchall()
        return [record_to_job(row) for row in rows]

    async def delete_job(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._delete_job_sync, job_id)

    def _delete_job_sync(self, job_id: str) -> Job:
        with self._connection_pool.connection() as connection:
            row = connection.execute(
                f"DELETE FROM jobs WHERE id = %s RETURNING {_JOB_COLUMNS}",
                (job_id,),
            ).fetchone()
            connection.commit()
        if row is None:
            raise KeyError(job_id)
        return record_to_job(row)

    async def list_due_time_jobs(self, *, now: datetime) -> list[Job]:
        return await asyncio.to_thread(self._list_due_time_jobs_sync, now)

    def _list_due_time_jobs_sync(self, now: datetime) -> list[Job]:
        with self._connection_pool.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_JOB_COLUMNS}
                FROM jobs
                WHERE trigger_type = 'time'
                  AND enabled = true
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= %s
                ORDER BY next_run_at ASC
                """,
                (dt_to_iso(now),),
            ).fetchall()
        return [record_to_job(row) for row in rows]

    async def list_event_jobs_for_subscription(self, subscription_id: str) -> list[Job]:
        return await asyncio.to_thread(
            self._list_event_jobs_for_subscription_sync,
            subscription_id,
        )

    def _list_event_jobs_for_subscription_sync(self, subscription_id: str) -> list[Job]:
        with self._connection_pool.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_JOB_COLUMNS}
                FROM jobs
                WHERE trigger_type = 'event'
                  AND enabled = true
                  AND subscription_id = %s
                """,
                (subscription_id,),
            ).fetchall()
        return [record_to_job(row) for row in rows]

    async def list_enabled_event_jobs(self) -> list[Job]:
        return await asyncio.to_thread(self._list_enabled_event_jobs_sync)

    def _list_enabled_event_jobs_sync(self) -> list[Job]:
        with self._connection_pool.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {_JOB_COLUMNS}
                FROM jobs
                WHERE trigger_type = 'event'
                  AND enabled = true
                """
            ).fetchall()
        return [record_to_job(row) for row in rows]

    async def set_subscription_id(self, job_id: str, subscription_id: str | None) -> None:
        await asyncio.to_thread(self._set_subscription_id_sync, job_id, subscription_id)

    def _set_subscription_id_sync(self, job_id: str, subscription_id: str | None) -> None:
        now = utc_now()
        with self._connection_pool.connection() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET subscription_id = %s, updated_at = %s
                WHERE id = %s
                """,
                (subscription_id, dt_to_iso(now), job_id),
            )
            connection.commit()

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
        await asyncio.to_thread(
            self._mark_time_job_result_sync,
            job,
            now,
            success,
            error,
            response_text,
            last_fetch_value,
        )

    def _mark_time_job_result_sync(
        self,
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

        self._update_job_result(
            job_id=job.id,
            now=now,
            success=success,
            error=error,
            response_text=response_text,
            last_fetch_value=last_fetch_value,
            extra_values={
                "next_run_at": dt_to_iso(next_run_at),
                "enabled": enabled,
            },
        )

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
        await asyncio.to_thread(
            self._update_job_result,
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
        await asyncio.to_thread(
            self._update_job_result,
            job_id=job_id,
            now=now,
            success=success,
            error=error,
            response_text=response_text,
            last_fetch_value=last_fetch_value,
        )

    def _update_job_result(
        self,
        *,
        job_id: str,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None,
        extra_values: dict[str, Any] | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "last_run_at": dt_to_iso(now),
            "last_error": None if success else error,
            "last_response": response_text if success else None,
            "updated_at": dt_to_iso(now),
        }
        if last_fetch_value is not None:
            values["last_fetch_value"] = last_fetch_value
        if extra_values:
            values.update(extra_values)

        assignments = [f"{name} = %s" for name in values]
        params = list(values.values())
        with self._connection_pool.connection() as connection:
            connection.execute(
                f"""
                UPDATE jobs
                SET {", ".join(assignments)},
                    run_count = run_count + 1
                WHERE id = %s
                """,
                (*params, job_id),
            )
            connection.commit()
