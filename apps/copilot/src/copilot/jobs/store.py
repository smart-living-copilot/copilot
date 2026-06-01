from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
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


class JobNotWaitingForInput(RuntimeError):
    """Raised when a job reply is submitted outside a waiting state."""


class JobRunNotCancellable(RuntimeError):
    """Raised when a job has no active run to cancel."""


_UNSET: object = object()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=True, default=str))


def job_thread_id_for_job(job_id: str) -> str:
    return f"job:{job_id}"


def _source_thread_id_for_job(request: CreateJobRequest, job_id: str) -> str:
    source_thread_id = (request.created_from_thread_id or "").strip()
    if source_thread_id:
        return source_thread_id
    return f"manual:{job_id}"


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
        active_run_id=row.active_run_id,
        active_run_started_at=row.active_run_started_at,
        active_run_source=JobRunSource(row.active_run_source)
        if row.active_run_source
        else None,
        waiting_question=row.waiting_question,
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
        created_from_thread_id = _source_thread_id_for_job(request, job_id)
        with self._session_factory() as session:
            row = JobRecord(
                id=job_id,
                name=request.name,
                created_from_thread_id=created_from_thread_id,
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

    async def get_job_by_thread_id(self, job_thread_id: str) -> Job:
        return await asyncio.to_thread(self._get_job_by_thread_id_sync, job_thread_id)

    def _get_job_by_thread_id_sync(self, job_thread_id: str) -> Job:
        statement = select(JobRecord).where(JobRecord.job_thread_id == job_thread_id)
        with self._session_factory() as session:
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_thread_id)
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

    async def update_job(
        self,
        job_id: str,
        *,
        name: object = _UNSET,
        prompt: object = _UNSET,
        analysis_code: object = _UNSET,
        interval_seconds: object = _UNSET,
        run_at: object = _UNSET,
        enabled: object = _UNSET,
    ) -> Job:
        return await asyncio.to_thread(
            self._update_job_sync,
            job_id,
            name,
            prompt,
            analysis_code,
            interval_seconds,
            run_at,
            enabled,
        )

    def _update_job_sync(
        self,
        job_id: str,
        name: object,
        prompt: object,
        analysis_code: object,
        interval_seconds: object,
        run_at: object,
        enabled: object,
    ) -> Job:
        now = utc_now()
        with self._session_factory() as session:
            statement = select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_id)

            if name is not _UNSET:
                row.name = name  # type: ignore[assignment]
            if prompt is not _UNSET:
                row.prompt = prompt  # type: ignore[assignment]
            if analysis_code is not _UNSET:
                row.analysis_code = analysis_code  # type: ignore[assignment]
            if interval_seconds is not _UNSET:
                row.interval_seconds = interval_seconds  # type: ignore[assignment]
            if run_at is not _UNSET:
                row.run_at = run_at  # type: ignore[assignment]
            if enabled is not _UNSET:
                row.enabled = bool(enabled)

            row.next_run_at = self._compute_next_run_at(row, now)
            row.updated_at = now
            session.commit()
            return _to_job(row)

    @staticmethod
    def _compute_next_run_at(row: JobRecord, now: datetime) -> datetime | None:
        if row.trigger_kind != JobTriggerKind.TIME.value or not row.enabled:
            return None
        if row.schedule_kind == TimeTriggerKind.INTERVAL.value and row.interval_seconds:
            return now + timedelta(seconds=row.interval_seconds)
        if row.schedule_kind == TimeTriggerKind.ONCE.value and row.run_at is not None:
            run_at = row.run_at
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
            return run_at if run_at > now else None
        return None

    async def cancel_active_run(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._cancel_active_run_sync, job_id)

    def _cancel_active_run_sync(self, job_id: str) -> Job:
        now = utc_now()
        with self._session_factory() as session:
            statement = select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_id)
            if row.active_run_id is None or row.last_run_status not in (
                JobRunStatus.RUNNING.value,
                JobRunStatus.WAITING_FOR_INPUT.value,
            ):
                raise JobRunNotCancellable(job_id)

            run_row = session.get(JobRunRecord, row.active_run_id)
            if run_row is not None:
                run_row.status = JobRunStatus.CANCELLED.value
                run_row.error = "Run cancelled by user."
                run_row.finished_at = now

            row.last_run_status = JobRunStatus.CANCELLED.value
            row.last_error = None
            row.active_run_id = None
            row.active_run_started_at = None
            row.active_run_source = None
            row.waiting_question = None
            row.run_count = (row.run_count or 0) + 1
            row.updated_at = now
            session.commit()
            return _to_job(row)

    async def try_start_job_run(
        self,
        *,
        job_id: str,
        source: JobRunSource,
        trigger_payload: dict,
        now: datetime,
    ) -> JobRun | None:
        return await asyncio.to_thread(
            self._try_start_job_run_sync,
            job_id,
            source,
            trigger_payload,
            now,
        )

    def _try_start_job_run_sync(
        self,
        job_id: str,
        source: JobRunSource,
        trigger_payload: dict,
        now: datetime,
    ) -> JobRun | None:
        with self._session_factory() as session:
            statement = select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_id)

            if source != JobRunSource.MANUAL and not row.enabled:
                run = self._create_skipped_run(
                    session,
                    row,
                    source,
                    trigger_payload,
                    now,
                    error="Job is disabled.",
                    response_text="Job is disabled.",
                    update_job_snapshot=True,
                )
                session.commit()
                return _to_job_run(run)

            if _has_active_run(row):
                run = self._create_skipped_run(
                    session,
                    row,
                    source,
                    trigger_payload,
                    now,
                    error="Job already has an active run.",
                    response_text="Job already has an active run.",
                    update_job_snapshot=False,
                )
                session.commit()
                return _to_job_run(run)

            run = JobRunRecord(
                id=str(uuid4()),
                job_id=row.id,
                job_thread_id=row.job_thread_id,
                source=source.value,
                status=JobRunStatus.RUNNING.value,
                trigger_payload=_json_safe(trigger_payload),
                started_at=now,
                created_at=now,
            )
            session.add(run)
            row.active_run_id = run.id
            row.active_run_started_at = now
            row.active_run_source = source.value
            row.last_run_id = run.id
            row.last_run_at = now
            row.last_run_status = JobRunStatus.RUNNING.value
            row.last_error = None
            row.updated_at = now
            session.commit()
            return _to_job_run(run)

    async def start_reply_job_run(
        self,
        *,
        job_id: str,
        message: str,
        previous_run_id: str | None,
        now: datetime,
    ) -> JobRun:
        return await asyncio.to_thread(
            self._start_reply_job_run_sync,
            job_id,
            message,
            previous_run_id,
            now,
        )

    def _start_reply_job_run_sync(
        self,
        job_id: str,
        message: str,
        previous_run_id: str | None,
        now: datetime,
    ) -> JobRun:
        with self._session_factory() as session:
            statement = select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_id)
            if row.last_run_status != JobRunStatus.WAITING_FOR_INPUT.value:
                raise JobNotWaitingForInput(job_id)

            trigger_payload = {
                "source": "user_reply",
                "message": message,
                "previous_run_id": previous_run_id or row.active_run_id or row.last_run_id,
            }
            run = JobRunRecord(
                id=str(uuid4()),
                job_id=row.id,
                job_thread_id=row.job_thread_id,
                source=JobRunSource.MANUAL.value,
                status=JobRunStatus.RUNNING.value,
                trigger_payload=_json_safe(trigger_payload),
                started_at=now,
                created_at=now,
            )
            session.add(run)
            row.active_run_id = run.id
            row.active_run_started_at = now
            row.active_run_source = JobRunSource.MANUAL.value
            row.last_run_id = run.id
            row.last_run_at = now
            row.last_run_status = JobRunStatus.RUNNING.value
            row.last_error = None
            row.updated_at = now
            session.commit()
            return _to_job_run(run)

    async def finish_job_run(
        self,
        *,
        run_id: str,
        job_id: str,
        now: datetime,
        status: JobRunStatus,
        error: str | None,
        response_text: str | None,
        result: dict | None,
        next_run_at: datetime | None = None,
        waiting_question: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._finish_job_run_sync,
            run_id,
            job_id,
            now,
            status,
            error,
            response_text,
            result,
            next_run_at,
            waiting_question,
        )

    def _finish_job_run_sync(
        self,
        run_id: str,
        job_id: str,
        now: datetime,
        status: JobRunStatus,
        error: str | None,
        response_text: str | None,
        result: dict | None,
        next_run_at: datetime | None,
        waiting_question: str | None,
    ) -> None:
        with self._session_factory() as session:
            run_statement = select(JobRunRecord).where(JobRunRecord.id == run_id).with_for_update()
            run_row = session.scalars(run_statement).one_or_none()
            if run_row is not None:
                run_row.status = status.value
                run_row.error = error
                run_row.response_text = response_text
                run_row.result = _json_safe(result) if result is not None else None
                run_row.finished_at = now

            job_statement = select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            job_row = session.scalars(job_statement).one_or_none()
            if job_row is None:
                session.commit()
                return

            job_row.last_run_id = run_id
            job_row.last_run_at = now
            job_row.last_run_status = status.value
            job_row.last_error = error if status == JobRunStatus.FAILED else None
            job_row.last_response = response_text if status != JobRunStatus.FAILED else None
            job_row.updated_at = now
            if next_run_at is not None:
                job_row.next_run_at = next_run_at
            job_row.run_count = (job_row.run_count or 0) + 1
            if status == JobRunStatus.WAITING_FOR_INPUT:
                job_row.active_run_id = run_id
                job_row.active_run_started_at = run_row.started_at if run_row is not None else now
                job_row.active_run_source = run_row.source if run_row is not None else None
                job_row.waiting_question = waiting_question or response_text
            else:
                if job_row.active_run_id == run_id:
                    job_row.active_run_id = None
                    job_row.active_run_started_at = None
                    job_row.active_run_source = None
                job_row.waiting_question = None
            session.commit()

    async def mark_stale_running_runs_failed(
        self,
        *,
        cutoff: datetime,
        now: datetime | None = None,
    ) -> int:
        return await asyncio.to_thread(
            self._mark_stale_running_runs_failed_sync,
            cutoff,
            now or utc_now(),
        )

    def _mark_stale_running_runs_failed_sync(self, cutoff: datetime, now: datetime) -> int:
        stale_error = "Job run exceeded its lease and was marked failed on startup."
        with self._session_factory() as session:
            statement = (
                select(JobRecord)
                .where(
                    JobRecord.active_run_id.is_not(None),
                    JobRecord.active_run_started_at < cutoff,
                    JobRecord.last_run_status == JobRunStatus.RUNNING.value,
                )
                .with_for_update()
            )
            jobs = session.scalars(statement).all()
            count = 0
            for job_row in jobs:
                run_row = session.get(JobRunRecord, job_row.active_run_id)
                if run_row is not None:
                    run_row.status = JobRunStatus.FAILED.value
                    run_row.error = stale_error
                    run_row.finished_at = now

                job_row.last_run_status = JobRunStatus.FAILED.value
                job_row.last_error = stale_error
                job_row.active_run_id = None
                job_row.active_run_started_at = None
                job_row.active_run_source = None
                job_row.waiting_question = None
                job_row.updated_at = now
                job_row.run_count = (job_row.run_count or 0) + 1
                count += 1
            session.commit()
            return count

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

    async def get_job_run(self, run_id: str) -> JobRun:
        return await asyncio.to_thread(self._get_job_run_sync, run_id)

    def _get_job_run_sync(self, run_id: str) -> JobRun:
        with self._session_factory() as session:
            row = session.get(JobRunRecord, run_id)
            if row is None:
                raise KeyError(run_id)
            return _to_job_run(row)

    def _create_skipped_run(
        self,
        session: Session,
        job_row: JobRecord,
        source: JobRunSource,
        trigger_payload: dict,
        now: datetime,
        *,
        error: str,
        response_text: str,
        update_job_snapshot: bool,
    ) -> JobRunRecord:
        run = JobRunRecord(
            id=str(uuid4()),
            job_id=job_row.id,
            job_thread_id=job_row.job_thread_id,
            source=source.value,
            status=JobRunStatus.SKIPPED.value,
            trigger_payload=_json_safe(trigger_payload),
            result=_json_safe({"ok": False, "status": JobRunStatus.SKIPPED.value}),
            error=error,
            response_text=response_text,
            started_at=now,
            finished_at=now,
            created_at=now,
        )
        session.add(run)
        job_row.run_count = (job_row.run_count or 0) + 1
        job_row.updated_at = now
        if update_job_snapshot:
            job_row.last_run_id = run.id
            job_row.last_run_at = now
            job_row.last_run_status = JobRunStatus.SKIPPED.value
            job_row.last_error = error
            job_row.last_response = response_text
        return run


def _has_active_run(row: JobRecord) -> bool:
    return bool(row.active_run_id) or row.last_run_status in {
        JobRunStatus.RUNNING.value,
        JobRunStatus.WAITING_FOR_INPUT.value,
    }
