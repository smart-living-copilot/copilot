from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from wotbot.jobs.db import JobRunEventRecord
from wotbot.jobs.enums import JobRunEventType, JobRunStatus
from wotbot.jobs.record_summary import submitted_record_event_message
from wotbot.jobs.stores.base import _json_safe


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
            message=submitted_record_event_message(submitted_record),
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
