from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from copilot.core.database import get_session_factory
from copilot.jobs.models import (
    CreateJobRequest,
    Job,
    JobActionKind,
    JobRecord,
    JobRun,
    JobRunRecord,
    JobRunSource,
    JobRunStatus,
    JobTriggerKind,
    TimeTriggerKind,
)
from copilot.threads.models import DEFAULT_THREAD_TITLE, Thread, ThreadKind


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=True, default=str))


def job_thread_id_for_job(job_id: str) -> str:
    return f"job:{job_id}"


def _to_job(row: JobRecord) -> Job:
    return Job(
        id=row.id,
        name=row.name,
        created_from_thread_id=row.created_from_thread_id,
        job_thread_id=row.job_thread_id,
        action_kind=JobActionKind(row.action_kind),
        prompt=row.prompt,
        analysis_code=row.analysis_code,
        enabled=row.enabled,
        trigger_kind=JobTriggerKind(row.trigger_kind),
        schedule_kind=TimeTriggerKind(row.schedule_kind) if row.schedule_kind else None,
        run_at=row.run_at,
        interval_seconds=row.interval_seconds,
        next_run_at=row.next_run_at,
        thing_id=row.thing_id,
        event_name=row.event_name,
        subscription_id=row.subscription_id,
        subscription_input=row.subscription_input,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_run_id=row.last_run_id,
        last_run_at=row.last_run_at,
        last_run_status=JobRunStatus(row.last_run_status) if row.last_run_status else None,
        last_error=row.last_error,
        last_response=row.last_response,
        run_count=row.run_count or 0,
        last_fetch_value=row.last_fetch_value,
    )


def _to_job_run(row: JobRunRecord) -> JobRun:
    return JobRun(
        id=row.id,
        job_id=row.job_id,
        job_thread_id=row.job_thread_id,
        source=JobRunSource(row.source),
        status=JobRunStatus(row.status),
        trigger_payload=row.trigger_payload,
        result=row.result,
        error=row.error,
        response_text=row.response_text,
        last_fetch_value=row.last_fetch_value,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
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
        now = utc_now()
        job_id = str(uuid4())
        job_thread_id = job_thread_id_for_job(job_id)
        with self._session_factory() as session:
            row = JobRecord(
                id=job_id,
                name=request.name,
                created_from_thread_id=request.created_from_thread_id,
                job_thread_id=job_thread_id,
                action_kind=request.action_kind.value,
                prompt=request.prompt,
                analysis_code=request.analysis_code,
                enabled=True,
                trigger_kind=request.trigger_kind.value,
                schedule_kind=request.schedule_kind.value if request.schedule_kind else None,
                run_at=request.run_at,
                interval_seconds=request.interval_seconds,
                next_run_at=next_run_at,
                thing_id=request.thing_id,
                event_name=request.event_name,
                subscription_id=subscription_id,
                subscription_input=_json_safe(request.subscription_input)
                if request.subscription_input is not None
                else None,
                created_at=now,
                updated_at=now,
                run_count=0,
            )
            thread = Thread(
                id=job_thread_id,
                title=f"Job: {request.name}"[:120] or DEFAULT_THREAD_TITLE,
                created_at=iso(now),
                updated_at=iso(now),
                kind=ThreadKind.JOB.value,
                visible=False,
                job_id=job_id,
            )
            session.add(row)
            session.add(thread)
            session.commit()
            return _to_job(row)

    async def get_job(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._get_job_sync, job_id)

    def _get_job_sync(self, job_id: str) -> Job:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise KeyError(job_id)
            return _to_job(row)

    async def list_jobs(self, created_from_thread_id: str | None = None) -> list[Job]:
        return await asyncio.to_thread(self._list_jobs_sync, created_from_thread_id)

    def _list_jobs_sync(self, created_from_thread_id: str | None = None) -> list[Job]:
        statement = select(JobRecord)
        if created_from_thread_id:
            statement = statement.where(
                JobRecord.created_from_thread_id == created_from_thread_id
            )
        statement = statement.order_by(JobRecord.created_at.desc())
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def delete_job(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._delete_job_sync, job_id)

    def _delete_job_sync(self, job_id: str) -> Job:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise KeyError(job_id)
            job = _to_job(row)
            thread = session.get(Thread, job.job_thread_id)
            if thread is not None:
                session.delete(thread)
            session.delete(row)
            session.commit()
            return job

    async def list_enabled_time_jobs(self) -> list[Job]:
        return await asyncio.to_thread(self._list_enabled_time_jobs_sync)

    def _list_enabled_time_jobs_sync(self) -> list[Job]:
        statement = (
            select(JobRecord)
            .where(
                JobRecord.trigger_kind == JobTriggerKind.TIME.value,
                JobRecord.enabled.is_(True),
            )
            .order_by(JobRecord.created_at.asc())
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def disable_job(self, job_id: str) -> None:
        await asyncio.to_thread(self._disable_job_sync, job_id)

    def _disable_job_sync(self, job_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                return
            row.enabled = False
            row.next_run_at = None
            row.updated_at = utc_now()
            session.commit()

    async def list_event_jobs_for_subscription(self, subscription_id: str) -> list[Job]:
        return await asyncio.to_thread(
            self._list_event_jobs_for_subscription_sync, subscription_id
        )

    def _list_event_jobs_for_subscription_sync(self, subscription_id: str) -> list[Job]:
        statement = select(JobRecord).where(
            JobRecord.trigger_kind == JobTriggerKind.EVENT.value,
            JobRecord.enabled.is_(True),
            JobRecord.subscription_id == subscription_id,
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def list_enabled_event_jobs(self) -> list[Job]:
        return await asyncio.to_thread(self._list_enabled_event_jobs_sync)

    def _list_enabled_event_jobs_sync(self) -> list[Job]:
        statement = select(JobRecord).where(
            JobRecord.trigger_kind == JobTriggerKind.EVENT.value,
            JobRecord.enabled.is_(True),
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def set_subscription_id(self, job_id: str, subscription_id: str | None) -> None:
        await asyncio.to_thread(self._set_subscription_id_sync, job_id, subscription_id)

    def _set_subscription_id_sync(self, job_id: str, subscription_id: str | None) -> None:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                return
            row.subscription_id = subscription_id
            row.updated_at = utc_now()
            session.commit()

    async def create_job_run(
        self,
        *,
        job: Job,
        source: JobRunSource,
        trigger_payload: dict,
        now: datetime,
    ) -> JobRun:
        return await asyncio.to_thread(
            self._create_job_run_sync,
            job,
            source,
            trigger_payload,
            now,
        )

    def _create_job_run_sync(
        self,
        job: Job,
        source: JobRunSource,
        trigger_payload: dict,
        now: datetime,
    ) -> JobRun:
        with self._session_factory() as session:
            row = JobRunRecord(
                id=str(uuid4()),
                job_id=job.id,
                job_thread_id=job.job_thread_id,
                source=source.value,
                status=JobRunStatus.RUNNING.value,
                trigger_payload=_json_safe(trigger_payload),
                started_at=now,
                created_at=now,
            )
            session.add(row)
            session.commit()
            return _to_job_run(row)

    async def record_job_result(
        self,
        *,
        run_id: str,
        job_id: str,
        now: datetime,
        status: JobRunStatus,
        error: str | None,
        response_text: str | None,
        result: dict | None,
        last_fetch_value: str | None = None,
        next_run_at: datetime | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_job_result_sync,
            run_id,
            job_id,
            now,
            status,
            error,
            response_text,
            result,
            last_fetch_value,
            next_run_at,
        )

    def _record_job_result_sync(
        self,
        run_id: str,
        job_id: str,
        now: datetime,
        status: JobRunStatus,
        error: str | None,
        response_text: str | None,
        result: dict | None,
        last_fetch_value: str | None,
        next_run_at: datetime | None,
    ) -> None:
        with self._session_factory() as session:
            run_row = session.get(JobRunRecord, run_id)
            if run_row is not None:
                run_row.status = status.value
                run_row.error = error
                run_row.response_text = response_text
                run_row.result = _json_safe(result) if result is not None else None
                run_row.last_fetch_value = last_fetch_value
                run_row.finished_at = now

            job_row = session.get(JobRecord, job_id)
            if job_row is None:
                session.commit()
                return

            job_row.last_run_id = run_id
            job_row.last_run_at = now
            job_row.last_run_status = status.value
            job_row.last_error = error if status == JobRunStatus.FAILED else None
            job_row.last_response = response_text if status != JobRunStatus.FAILED else None
            job_row.updated_at = now
            if last_fetch_value is not None:
                job_row.last_fetch_value = last_fetch_value
            if next_run_at is not None:
                job_row.next_run_at = next_run_at
            job_row.run_count = (job_row.run_count or 0) + 1
            session.commit()

    async def list_job_runs(self, job_id: str) -> list[JobRun]:
        return await asyncio.to_thread(self._list_job_runs_sync, job_id)

    def _list_job_runs_sync(self, job_id: str) -> list[JobRun]:
        statement = (
            select(JobRunRecord)
            .where(JobRunRecord.job_id == job_id)
            .order_by(JobRunRecord.started_at.desc())
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job_run(row) for row in rows]
