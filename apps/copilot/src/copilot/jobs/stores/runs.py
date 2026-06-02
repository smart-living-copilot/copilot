from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from copilot.jobs.models import (
    Job,
    JobRecord,
    JobRun,
    JobRunEventType,
    JobRunRecord,
    JobRunSource,
    JobRunStatus,
)
from copilot.jobs.stores.base import (
    _JobStoreBase,
    _add_finish_events,
    _add_job_run_event,
    _duplicate_reply_run,
    _has_active_run,
    _job_thread_id_for_run_row,
    _json_safe,
    _normalize_client_reply_id,
    _reply_payload_has_client_reply_id,
    _to_job,
    _to_job_run,
    iso,
    JobNotWaitingForInput,
    JobRunNotCancellable,
    utc_now,
)

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
