from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from copilot.core.database import get_session_factory
from copilot.jobs.db import JobRecord, JobRunEventRecord, JobRunRecord
from copilot.jobs.enums import (
    JobActionKind,
    JobInteractionMode,
    JobOutputKind,
    JobRunEventType,
    JobRunSource,
    JobRunStatus,
    JobTriggerKind,
    TimeTriggerKind,
)
from copilot.jobs.schemas import CreateJobRequest, Job, JobRun, JobRunEvent

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
        cron_expression=row.cron_expression,
        cron_timezone=row.cron_timezone,
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
