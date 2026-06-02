from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

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
