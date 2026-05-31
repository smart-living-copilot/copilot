from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from copilot.core.database import get_session_factory
from copilot.jobs.models import CreateJobRequest, Job, JobRow


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return iso(value)


def iso_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _to_job(row: JobRow) -> Job:
    return Job(
        id=row.id,
        name=row.name,
        thread_id=row.thread_id,
        job_type=cast('Literal["prompt", "analysis"]', row.job_type),
        prompt=row.prompt,
        analysis_code=row.analysis_code,
        enabled=row.enabled,
        trigger_type=cast('Literal["time", "event"]', row.trigger_type),
        run_at=iso_to_dt(row.run_at),
        interval_seconds=row.interval_seconds,
        next_run_at=iso_to_dt(row.next_run_at),
        thing_id=row.thing_id,
        event_name=row.event_name,
        subscription_id=row.subscription_id,
        subscription_input=json.loads(row.subscription_input_json)
        if row.subscription_input_json
        else None,
        created_at=iso_to_dt(row.created_at) or utc_now(),
        updated_at=iso_to_dt(row.updated_at) or utc_now(),
        last_run_at=iso_to_dt(row.last_run_at),
        last_error=row.last_error,
        last_response=row.last_response,
        run_count=row.run_count or 0,
        last_fetch_value=row.last_fetch_value,
    )


class JobStore:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def create_job(
        self,
        request: CreateJobRequest,
        *,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        return await asyncio.to_thread(
            self._create_job_sync, request, next_run_at, subscription_id
        )

    def _create_job_sync(
        self,
        request: CreateJobRequest,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        now = iso(utc_now())
        subscription_input_json = (
            json.dumps(request.subscription_input)
            if request.subscription_input is not None
            else None
        )
        with self._session_factory() as session:
            row = JobRow(
                id=str(uuid4()),
                name=request.name,
                thread_id=request.thread_id,
                job_type=request.job_type,
                prompt=request.prompt or "",
                analysis_code=request.analysis_code,
                enabled=True,
                trigger_type=request.trigger_type,
                run_at=dt_to_iso(request.run_at),
                interval_seconds=request.interval_seconds,
                next_run_at=dt_to_iso(next_run_at),
                thing_id=request.thing_id,
                event_name=request.event_name,
                subscription_id=subscription_id,
                subscription_input_json=subscription_input_json,
                created_at=now,
                updated_at=now,
                run_count=0,
            )
            session.add(row)
            session.commit()
            return _to_job(row)

    async def get_job(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._get_job_sync, job_id)

    def _get_job_sync(self, job_id: str) -> Job:
        with self._session_factory() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                raise KeyError(job_id)
            return _to_job(row)

    async def list_jobs(self, thread_id: str | None = None) -> list[Job]:
        return await asyncio.to_thread(self._list_jobs_sync, thread_id)

    def _list_jobs_sync(self, thread_id: str | None = None) -> list[Job]:
        statement = select(JobRow)
        if thread_id:
            statement = statement.where(JobRow.thread_id == thread_id)
        statement = statement.order_by(JobRow.created_at.desc())
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def delete_job(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._delete_job_sync, job_id)

    def _delete_job_sync(self, job_id: str) -> Job:
        with self._session_factory() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                raise KeyError(job_id)
            job = _to_job(row)
            session.delete(row)
            session.commit()
            return job

    async def list_enabled_time_jobs(self) -> list[Job]:
        return await asyncio.to_thread(self._list_enabled_time_jobs_sync)

    def _list_enabled_time_jobs_sync(self) -> list[Job]:
        statement = (
            select(JobRow)
            .where(JobRow.trigger_type == "time", JobRow.enabled.is_(True))
            .order_by(JobRow.created_at.asc())
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def disable_job(self, job_id: str) -> None:
        await asyncio.to_thread(self._disable_job_sync, job_id)

    def _disable_job_sync(self, job_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                return
            row.enabled = False
            row.next_run_at = None
            row.updated_at = iso(utc_now())
            session.commit()

    async def list_event_jobs_for_subscription(self, subscription_id: str) -> list[Job]:
        return await asyncio.to_thread(
            self._list_event_jobs_for_subscription_sync, subscription_id
        )

    def _list_event_jobs_for_subscription_sync(self, subscription_id: str) -> list[Job]:
        statement = select(JobRow).where(
            JobRow.trigger_type == "event",
            JobRow.enabled.is_(True),
            JobRow.subscription_id == subscription_id,
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def list_enabled_event_jobs(self) -> list[Job]:
        return await asyncio.to_thread(self._list_enabled_event_jobs_sync)

    def _list_enabled_event_jobs_sync(self) -> list[Job]:
        statement = select(JobRow).where(
            JobRow.trigger_type == "event", JobRow.enabled.is_(True)
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def set_subscription_id(self, job_id: str, subscription_id: str | None) -> None:
        await asyncio.to_thread(self._set_subscription_id_sync, job_id, subscription_id)

    def _set_subscription_id_sync(self, job_id: str, subscription_id: str | None) -> None:
        with self._session_factory() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                return
            row.subscription_id = subscription_id
            row.updated_at = iso(utc_now())
            session.commit()

    async def record_job_result(
        self,
        *,
        job_id: str,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None = None,
        next_run_at: datetime | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_job_result_sync,
            job_id,
            now,
            success,
            error,
            response_text,
            last_fetch_value,
            next_run_at,
        )

    def _record_job_result_sync(
        self,
        job_id: str,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None,
        next_run_at: datetime | None,
    ) -> None:
        now_iso = iso(now)
        with self._session_factory() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                return
            row.last_run_at = now_iso
            row.last_error = None if success else error
            row.last_response = response_text if success else None
            row.updated_at = now_iso
            if last_fetch_value is not None:
                row.last_fetch_value = last_fetch_value
            if next_run_at is not None:
                row.next_run_at = dt_to_iso(next_run_at)
            row.run_count = (row.run_count or 0) + 1
            session.commit()
