from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

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


class Job(BaseModel):
    """API model for a persisted automation job and its latest run snapshot."""

    id: str
    name: str
    created_from_thread_id: str
    job_thread_id: str
    action_kind: JobActionKind = JobActionKind.PROMPT
    interaction_mode: JobInteractionMode = JobInteractionMode.AUTONOMOUS
    output_kind: JobOutputKind = JobOutputKind.NARRATIVE
    prompt: str | None = Field(
        default=None,
        description=(
            "Runtime instructions for the job. This is saved verbatim and must not "
            "include the user's request to create or schedule the job."
        ),
    )
    analysis_code: str | None = None
    record_schema: Any | None = None
    record_schema_version: int | None = None
    virtual_thing_id: str | None = None
    enabled: bool
    trigger_kind: JobTriggerKind
    schedule_kind: TimeTriggerKind | None = None
    run_at: datetime | None = None
    interval_seconds: int | None = None
    cron_expression: str | None = None
    cron_timezone: str | None = None
    next_run_at: datetime | None = None
    thing_id: str | None = None
    event_name: str | None = None
    subscription_id: str | None = None
    subscription_input: Any | None = None
    resource_health: Any | None = None
    created_at: datetime
    updated_at: datetime
    last_run_id: str | None = None
    last_run_at: datetime | None = None
    last_run_status: JobRunStatus | None = None
    last_error: str | None = None
    last_response: str | None = None
    run_count: int = 0
    active_run_id: str | None = None
    active_run_started_at: datetime | None = None
    active_run_source: JobRunSource | None = None
    waiting_question: str | None = None


class JobRun(BaseModel):
    """API model for one execution attempt of a job."""

    id: str
    job_id: str
    job_thread_id: str
    source: JobRunSource
    status: JobRunStatus
    trigger_payload: Any
    result: Any | None = None
    error: str | None = None
    response_text: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime


class JobRunEvent(BaseModel):
    """API model for a timeline entry emitted while a job run executes."""

    id: int
    job_id: str
    run_id: str
    event_type: JobRunEventType
    message: str | None = None
    payload: Any | None = None
    created_at: datetime


class CreateJobRequest(BaseModel):
    """Request payload for creating time or event triggered automation jobs."""

    name: str = Field(min_length=1, max_length=120)
    created_from_thread_id: str | None = Field(default=None, max_length=120)
    action_kind: JobActionKind = JobActionKind.PROMPT
    interaction_mode: JobInteractionMode = JobInteractionMode.AUTONOMOUS
    output_kind: JobOutputKind = JobOutputKind.NARRATIVE
    prompt: str | None = Field(
        default=None,
        description=(
            "Runtime instructions for the job. Do not include create/schedule job meta text."
        ),
    )
    analysis_code: str | None = None
    record_schema: Any | None = None
    record_schema_version: int | None = Field(default=None, ge=1)
    virtual_thing_id: str | None = Field(default=None, max_length=180)
    virtual_thing_title: str | None = Field(default=None, max_length=120)
    virtual_thing_description: str | None = None
    trigger_kind: JobTriggerKind

    schedule_kind: TimeTriggerKind | None = None
    run_at: datetime | None = None
    interval_seconds: int | None = Field(default=None, ge=1)
    cron_expression: str | None = Field(default=None, max_length=120)
    cron_timezone: str | None = Field(default=None, max_length=80)

    thing_id: str | None = None
    event_name: str | None = None
    subscription_input: Any | None = None


class UpdateJobRequest(BaseModel):
    """Partial update for an existing job.

    Only the editable surface is exposed: identity, action payload, the time
    schedule, and the enabled flag. The trigger/action kind and any event binding
    are immutable -- changing those requires recreating the job.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    prompt: str | None = Field(
        default=None,
        description=(
            "Runtime instructions for the job. Do not include create/schedule job meta text."
        ),
    )
    analysis_code: str | None = None
    schedule_kind: TimeTriggerKind | None = None
    interval_seconds: int | None = Field(default=None, ge=1)
    run_at: datetime | None = None
    cron_expression: str | None = Field(default=None, max_length=120)
    cron_timezone: str | None = Field(default=None, max_length=80)
    enabled: bool | None = None


class ReplyJobRequest(BaseModel):
    """User reply payload for resuming a job waiting for input."""

    message: str = Field(min_length=1, max_length=8000)
    client_reply_id: str | None = Field(default=None, min_length=1, max_length=120)
