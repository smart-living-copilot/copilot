from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from copilot.core.database import get_session_factory
from copilot.jobs.models import (
    CreateJobRequest,
    Job,
    JobActionKind,
    JobInteractionMode,
    JobOutputKind,
    JobRecord,
    JobRun,
    JobRunEvent,
    JobRunEventRecord,
    JobRunEventType,
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


def _updated_resource_health(
    current: Any,
    *,
    resource: str,
    status: str,
    message: str | None,
    now: datetime,
) -> dict[str, Any]:
    health = dict(current) if isinstance(current, dict) else {}
    resources = dict(health.get("resources")) if isinstance(health.get("resources"), dict) else {}
    entry: dict[str, Any] = {
        "status": status,
        "checked_at": iso(now),
    }
    if message:
        entry["message"] = message
    resources[resource] = entry

    has_degraded_resource = any(
        isinstance(value, dict) and value.get("status") == "degraded"
        for value in resources.values()
    )
    degraded_messages = [
        str(value.get("message") or "")
        for value in resources.values()
        if isinstance(value, dict) and value.get("status") == "degraded"
    ]
    degraded_messages = [message for message in degraded_messages if message]
    overall_status = "degraded" if has_degraded_resource else "healthy"
    updated: dict[str, Any] = {
        "status": overall_status,
        "checked_at": iso(now),
        "resources": resources,
    }
    if degraded_messages:
        updated["last_error"] = degraded_messages[-1]
    return _json_safe(updated)


def job_thread_id_for_job(job_id: str) -> str:
    return f"job:{job_id}"


def job_run_thread_id_for_run(job_id: str, run_id: str) -> str:
    return f"job:{job_id}:run:{run_id}"


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
        interaction_mode=JobInteractionMode(row.interaction_mode),
        output_kind=JobOutputKind(row.output_kind),
        prompt=row.prompt,
        analysis_code=row.analysis_code,
        record_schema=row.record_schema,
        record_schema_version=row.record_schema_version,
        virtual_thing_id=row.virtual_thing_id,
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
        resource_health=row.resource_health,
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


def _to_job_run_event(row: JobRunEventRecord) -> JobRunEvent:
    return JobRunEvent(
        id=row.id,
        job_id=row.job_id,
        run_id=row.run_id,
        event_type=JobRunEventType(row.event_type),
        message=row.message,
        payload=row.payload,
        created_at=row.created_at,
    )


class _JobStoreBase:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()


class JobDefinitionStore(_JobStoreBase):
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
                interaction_mode=request.interaction_mode.value,
                output_kind=request.output_kind.value,
                prompt=request.prompt,
                analysis_code=request.analysis_code,
                record_schema=_json_safe(request.record_schema)
                if request.record_schema is not None
                else None,
                record_schema_version=request.record_schema_version,
                virtual_thing_id=request.virtual_thing_id,
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
                resource_health=None,
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

    async def set_job_resource_health(
        self,
        job_id: str,
        *,
        resource: str,
        status: str,
        message: str | None = None,
        now: datetime | None = None,
    ) -> Job | None:
        return await asyncio.to_thread(
            self._set_job_resource_health_sync,
            job_id,
            resource,
            status,
            message,
            now or utc_now(),
        )

    def _set_job_resource_health_sync(
        self,
        job_id: str,
        resource: str,
        status: str,
        message: str | None,
        now: datetime,
    ) -> Job | None:
        with self._session_factory() as session:
            statement = select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            row = session.scalars(statement).one_or_none()
            if row is None:
                return None
            row.resource_health = _updated_resource_health(
                row.resource_health,
                resource=resource,
                status=status,
                message=message,
                now=now,
            )
            row.updated_at = now
            session.commit()
            return _to_job(row)

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


class JobRunStore(_JobStoreBase):
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
                _add_job_run_event(
                    session,
                    job_id=row.id,
                    run_id=run_row.id,
                    event_type=JobRunEventType.RUN_CANCELLED,
                    now=now,
                    message="Run cancelled by user.",
                )

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
                run = _create_skipped_run(
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
                run = _create_skipped_run(
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

            run_id = str(uuid4())
            run = JobRunRecord(
                id=run_id,
                job_id=row.id,
                job_thread_id=_job_thread_id_for_run_row(row, run_id),
                source=source.value,
                status=JobRunStatus.RUNNING.value,
                trigger_payload=_json_safe(trigger_payload),
                started_at=now,
                created_at=now,
            )
            session.add(run)
            session.flush()
            _add_job_run_event(
                session,
                job_id=row.id,
                run_id=run.id,
                event_type=JobRunEventType.RUN_STARTED,
                now=now,
                payload={
                    "source": source.value,
                    "trigger": trigger_payload,
                },
            )
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
        client_reply_id: str | None,
        previous_run_id: str | None,
        now: datetime,
    ) -> JobRun:
        return await asyncio.to_thread(
            self._start_reply_job_run_sync,
            job_id,
            message,
            client_reply_id,
            previous_run_id,
            now,
        )

    def _start_reply_job_run_sync(
        self,
        job_id: str,
        message: str,
        client_reply_id: str | None,
        previous_run_id: str | None,
        now: datetime,
    ) -> JobRun:
        client_reply_id = _normalize_client_reply_id(client_reply_id)
        with self._session_factory() as session:
            statement = select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_id)
            run_id = row.active_run_id or row.last_run_id
            if not run_id:
                raise KeyError(job_id)
            run_row = session.get(JobRunRecord, run_id)
            if run_row is None:
                raise KeyError(run_id)

            if client_reply_id and _reply_payload_has_client_reply_id(
                run_row.trigger_payload,
                client_reply_id,
            ):
                return _duplicate_reply_run(run_row)

            if row.last_run_status != JobRunStatus.WAITING_FOR_INPUT.value:
                raise JobNotWaitingForInput(job_id)

            trigger_payload = _json_safe(
                {
                    **(run_row.trigger_payload if isinstance(run_row.trigger_payload, dict) else {}),
                    "latest_reply": message,
                    "latest_reply_at": iso(now),
                    "replies": [
                        *(
                            run_row.trigger_payload.get("replies", [])
                            if run_row is not None
                            and isinstance(run_row.trigger_payload, dict)
                            and isinstance(run_row.trigger_payload.get("replies"), list)
                            else []
                        ),
                        {
                            "message": message,
                            "client_reply_id": client_reply_id,
                            "received_at": iso(now),
                            "previous_run_id": previous_run_id
                            or row.active_run_id
                            or row.last_run_id,
                        },
                    ],
                }
            )

            run_row.status = JobRunStatus.RUNNING.value
            run_row.trigger_payload = trigger_payload
            run_row.finished_at = None
            _add_job_run_event(
                session,
                job_id=row.id,
                run_id=run_row.id,
                event_type=JobRunEventType.USER_REPLY,
                now=now,
                message=message,
                payload={
                    "client_reply_id": client_reply_id,
                    "previous_run_id": previous_run_id
                    or row.active_run_id
                    or row.last_run_id,
                },
            )

            row.active_run_id = run_row.id
            row.active_run_started_at = now
            row.active_run_source = run_row.source
            row.last_run_id = run_row.id
            row.last_run_at = now
            row.last_run_status = JobRunStatus.RUNNING.value
            row.last_error = None
            row.waiting_question = None
            row.updated_at = now
            session.commit()
            return _to_job_run(run_row)

    async def get_active_or_last_job_run(self, job_id: str) -> JobRun:
        return await asyncio.to_thread(self._get_active_or_last_job_run_sync, job_id)

    def _get_active_or_last_job_run_sync(self, job_id: str) -> JobRun:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise KeyError(job_id)
            run_id = row.active_run_id or row.last_run_id
            if not run_id:
                raise KeyError(job_id)
            run = session.get(JobRunRecord, run_id)
            if run is None:
                raise KeyError(run_id)
            return _to_job_run(run)

    async def get_job_by_active_run_thread_id(self, job_thread_id: str) -> Job:
        return await asyncio.to_thread(
            self._get_job_by_active_run_thread_id_sync, job_thread_id
        )

    def _get_job_by_active_run_thread_id_sync(self, job_thread_id: str) -> Job:
        with self._session_factory() as session:
            statement = (
                select(JobRecord)
                .join(JobRunRecord, JobRunRecord.id == JobRecord.active_run_id)
                .where(JobRunRecord.job_thread_id == job_thread_id)
            )
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_thread_id)
            return _to_job(row)

    async def get_job_run(self, run_id: str) -> JobRun:
        return await asyncio.to_thread(self._get_job_run_sync, run_id)

    def _get_job_run_sync(self, run_id: str) -> JobRun:
        with self._session_factory() as session:
            row = session.get(JobRunRecord, run_id)
            if row is None:
                raise KeyError(run_id)
            return _to_job_run(row)

    async def get_job_run_by_client_reply_id(
        self,
        job_id: str,
        client_reply_id: str,
    ) -> JobRun | None:
        return await asyncio.to_thread(
            self._get_job_run_by_client_reply_id_sync,
            job_id,
            client_reply_id,
        )

    def _get_job_run_by_client_reply_id_sync(
        self,
        job_id: str,
        client_reply_id: str,
    ) -> JobRun | None:
        normalized = _normalize_client_reply_id(client_reply_id)
        if normalized is None:
            return None
        statement = (
            select(JobRunRecord)
            .where(JobRunRecord.job_id == job_id)
            .order_by(JobRunRecord.started_at.desc())
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            for row in rows:
                if _reply_payload_has_client_reply_id(row.trigger_payload, normalized):
                    return _duplicate_reply_run(row)
        return None

    async def get_latest_job_run(self, job_id: str) -> JobRun | None:
        return await asyncio.to_thread(self._get_latest_job_run_sync, job_id)

    def _get_latest_job_run_sync(self, job_id: str) -> JobRun | None:
        statement = (
            select(JobRunRecord)
            .where(JobRunRecord.job_id == job_id)
            .order_by(JobRunRecord.started_at.desc())
            .limit(1)
        )
        with self._session_factory() as session:
            row = session.scalars(statement).one_or_none()
            return _to_job_run(row) if row is not None else None

    async def get_job_by_thread_id_any(self, job_thread_id: str) -> Job:
        try:
            return await self.get_job_by_thread_id(job_thread_id)
        except KeyError:
            return await self.get_job_by_active_run_thread_id(job_thread_id)

    async def get_job_run_by_thread_id(self, job_thread_id: str) -> JobRun:
        return await asyncio.to_thread(self._get_job_run_by_thread_id_sync, job_thread_id)

    def _get_job_run_by_thread_id_sync(self, job_thread_id: str) -> JobRun:
        statement = select(JobRunRecord).where(JobRunRecord.job_thread_id == job_thread_id)
        with self._session_factory() as session:
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_thread_id)
            return _to_job_run(row)

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
            run_statement = (
                select(JobRunRecord).where(JobRunRecord.id == run_id).with_for_update()
            )
            run_row = session.scalars(run_statement).one_or_none()
            if run_row is not None:
                run_row.status = status.value
                run_row.error = error
                run_row.response_text = response_text
                run_row.result = _json_safe(result) if result is not None else None
                run_row.finished_at = None if status == JobRunStatus.WAITING_FOR_INPUT else now
                _add_finish_events(
                    session,
                    job_id=job_id,
                    run_id=run_id,
                    now=now,
                    status=status,
                    error=error,
                    response_text=response_text,
                    result=result,
                    waiting_question=waiting_question,
                )

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
            if status == JobRunStatus.WAITING_FOR_INPUT:
                job_row.active_run_id = run_id
                job_row.active_run_started_at = run_row.started_at if run_row is not None else now
                job_row.active_run_source = run_row.source if run_row is not None else None
                job_row.waiting_question = waiting_question or response_text
            else:
                job_row.run_count = (job_row.run_count or 0) + 1
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
                    _add_job_run_event(
                        session,
                        job_id=job_row.id,
                        run_id=run_row.id,
                        event_type=JobRunEventType.RUN_FAILED,
                        now=now,
                        message=stale_error,
                    )

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


class JobRunEventStore(_JobStoreBase):
    async def list_job_run_events(
        self,
        job_id: str,
        *,
        run_id: str | None = None,
    ) -> list[JobRunEvent]:
        return await asyncio.to_thread(self._list_job_run_events_sync, job_id, run_id)

    def _list_job_run_events_sync(
        self,
        job_id: str,
        run_id: str | None,
    ) -> list[JobRunEvent]:
        statement = select(JobRunEventRecord).where(JobRunEventRecord.job_id == job_id)
        if run_id is not None:
            statement = statement.where(JobRunEventRecord.run_id == run_id)
        statement = statement.order_by(
            JobRunEventRecord.created_at.asc(),
            JobRunEventRecord.id.asc(),
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job_run_event(row) for row in rows]

def _create_skipped_run(
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
    run_id = str(uuid4())
    run = JobRunRecord(
        id=run_id,
        job_id=job_row.id,
        job_thread_id=_job_thread_id_for_run_row(job_row, run_id),
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
    session.flush()
    _add_job_run_event(
        session,
        job_id=job_row.id,
        run_id=run.id,
        event_type=JobRunEventType.RUN_SKIPPED,
        now=now,
        message=response_text,
        payload={
            "source": source.value,
            "trigger": trigger_payload,
            "error": error,
        },
    )
    job_row.run_count = (job_row.run_count or 0) + 1
    job_row.updated_at = now
    if update_job_snapshot:
        job_row.last_run_id = run.id
        job_row.last_run_at = now
        job_row.last_run_status = JobRunStatus.SKIPPED.value
        job_row.last_error = error
        job_row.last_response = response_text
    return run


class JobStore(JobDefinitionStore, JobRunStore, JobRunEventStore):
    """Compatibility facade over the narrower job persistence stores."""


def _add_finish_events(
    session: Session,
    *,
    job_id: str,
    run_id: str,
    now: datetime,
    status: JobRunStatus,
    error: str | None,
    response_text: str | None,
    result: dict | None,
    waiting_question: str | None,
) -> None:
    if status == JobRunStatus.WAITING_FOR_INPUT:
        _add_job_run_event(
            session,
            job_id=job_id,
            run_id=run_id,
            event_type=JobRunEventType.WAITING_FOR_INPUT,
            now=now,
            message=waiting_question or response_text,
        )
        return

    submitted_record = _submitted_record_from_run_result(result)
    if submitted_record is not None:
        _add_job_run_event(
            session,
            job_id=job_id,
            run_id=run_id,
            event_type=JobRunEventType.RECORD_SUBMITTED,
            now=now,
            message="Structured record submitted.",
            payload=submitted_record,
        )

    if response_text:
        _add_job_run_event(
            session,
            job_id=job_id,
            run_id=run_id,
            event_type=JobRunEventType.ASSISTANT_MESSAGE,
            now=now,
            message=response_text,
        )

    if status == JobRunStatus.SUCCEEDED:
        _add_job_run_event(
            session,
            job_id=job_id,
            run_id=run_id,
            event_type=JobRunEventType.RUN_SUCCEEDED,
            now=now,
            message="Run succeeded.",
        )
    elif status == JobRunStatus.FAILED:
        _add_job_run_event(
            session,
            job_id=job_id,
            run_id=run_id,
            event_type=JobRunEventType.RUN_FAILED,
            now=now,
            message=error or "Run failed.",
        )
    elif status == JobRunStatus.CANCELLED:
        _add_job_run_event(
            session,
            job_id=job_id,
            run_id=run_id,
            event_type=JobRunEventType.RUN_CANCELLED,
            now=now,
            message=error or "Run cancelled.",
        )
    elif status == JobRunStatus.SKIPPED:
        _add_job_run_event(
            session,
            job_id=job_id,
            run_id=run_id,
            event_type=JobRunEventType.RUN_SKIPPED,
            now=now,
            message=error or response_text or "Run skipped.",
        )


def _submitted_record_from_run_result(result: dict | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    submitted_record = result.get("submitted_record")
    return submitted_record if isinstance(submitted_record, dict) else None


def _add_job_run_event(
    session: Session,
    *,
    job_id: str,
    run_id: str,
    event_type: JobRunEventType,
    now: datetime,
    message: str | None = None,
    payload: Any | None = None,
) -> None:
    session.add(
        JobRunEventRecord(
            job_id=job_id,
            run_id=run_id,
            event_type=event_type.value,
            message=message,
            payload=_json_safe(payload) if payload is not None else None,
            created_at=now,
        )
    )


def _normalize_client_reply_id(client_reply_id: str | None) -> str | None:
    normalized = (client_reply_id or "").strip()
    return normalized or None


def _reply_payload_has_client_reply_id(payload: Any, client_reply_id: str) -> bool:
    if not isinstance(payload, dict):
        return False
    replies = payload.get("replies")
    if not isinstance(replies, list):
        return False
    for reply in replies:
        if not isinstance(reply, dict):
            continue
        if reply.get("client_reply_id") == client_reply_id:
            return True
    return False


def _duplicate_reply_run(row: JobRunRecord) -> JobRun:
    run = _to_job_run(row)
    trigger_payload = run.trigger_payload if isinstance(run.trigger_payload, dict) else {}
    run.trigger_payload = {
        **trigger_payload,
        "_duplicate_reply": True,
    }
    return run


def _has_active_run(row: JobRecord) -> bool:
    return bool(row.active_run_id) or row.last_run_status in {
        JobRunStatus.RUNNING.value,
        JobRunStatus.WAITING_FOR_INPUT.value,
    }


def _job_thread_id_for_run_row(row: JobRecord, run_id: str) -> str:
    if row.action_kind == JobActionKind.PROMPT.value:
        return job_run_thread_id_for_run(row.id, run_id)
    return row.job_thread_id
