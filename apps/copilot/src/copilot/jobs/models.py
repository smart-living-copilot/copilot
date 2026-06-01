from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from copilot.core.orm import Base


class JobTriggerKind(StrEnum):
    TIME = "time"
    EVENT = "event"


class TimeTriggerKind(StrEnum):
    ONCE = "once"
    INTERVAL = "interval"


class JobActionKind(StrEnum):
    PROMPT = "prompt"
    ANALYSIS = "analysis"


class JobRunSource(StrEnum):
    MANUAL = "manual"
    TIME = "time"
    EVENT = "event"


class JobRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    WAITING_FOR_INPUT = "waiting_for_input"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class JobRecord(Base):
    """SQLAlchemy mapping for automation job definitions."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "action_kind IN ('prompt', 'analysis')",
            name="ck_jobs_action_kind",
        ),
        CheckConstraint(
            "trigger_kind IN ('time', 'event')",
            name="ck_jobs_trigger_kind",
        ),
        CheckConstraint(
            "schedule_kind IS NULL OR schedule_kind IN ('once', 'interval')",
            name="ck_jobs_schedule_kind",
        ),
        CheckConstraint(
            "last_run_status IS NULL OR last_run_status IN "
            "('running', 'succeeded', 'failed', 'waiting_for_input', 'cancelled', "
            "'skipped')",
            name="ck_jobs_last_run_status",
        ),
        CheckConstraint(
            "active_run_source IS NULL OR active_run_source IN ('manual', 'time', 'event')",
            name="ck_jobs_active_run_source",
        ),
        Index("idx_jobs_due", "trigger_kind", "enabled", "next_run_at"),
        Index("idx_jobs_created_from_thread", "created_from_thread_id"),
        Index("idx_jobs_subscription", "subscription_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_from_thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    job_thread_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    action_kind: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=JobActionKind.PROMPT.value,
    )
    prompt: Mapped[str | None] = mapped_column(Text)
    analysis_code: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_kind: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_kind: Mapped[str | None] = mapped_column(Text)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    thing_id: Mapped[str | None] = mapped_column(Text)
    event_name: Mapped[str | None] = mapped_column(Text)
    subscription_id: Mapped[str | None] = mapped_column(Text)
    subscription_input: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_id: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_status: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_response: Mapped[str | None] = mapped_column(Text)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_run_id: Mapped[str | None] = mapped_column(Text)
    active_run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_run_source: Mapped[str | None] = mapped_column(Text)
    waiting_question: Mapped[str | None] = mapped_column(Text)


class JobRunRecord(Base):
    """SQLAlchemy mapping for individual job executions."""

    __tablename__ = "job_runs"
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual', 'time', 'event')",
            name="ck_job_runs_source",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'waiting_for_input', "
            "'cancelled', 'skipped')",
            name="ck_job_runs_status",
        ),
        Index("idx_job_runs_job_started", "job_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_payload: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[Any | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Job(BaseModel):
    id: str
    name: str
    created_from_thread_id: str
    job_thread_id: str
    action_kind: JobActionKind = JobActionKind.PROMPT
    prompt: str | None = None
    analysis_code: str | None = None
    enabled: bool
    trigger_kind: JobTriggerKind
    schedule_kind: TimeTriggerKind | None = None
    run_at: datetime | None = None
    interval_seconds: int | None = None
    next_run_at: datetime | None = None
    thing_id: str | None = None
    event_name: str | None = None
    subscription_id: str | None = None
    subscription_input: Any | None = None
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


class CreateJobRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    created_from_thread_id: str | None = Field(default=None, max_length=120)
    action_kind: JobActionKind = JobActionKind.PROMPT
    prompt: str | None = None
    analysis_code: str | None = None
    trigger_kind: JobTriggerKind

    schedule_kind: TimeTriggerKind | None = None
    run_at: datetime | None = None
    interval_seconds: int | None = Field(default=None, ge=1)

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
    prompt: str | None = None
    analysis_code: str | None = None
    interval_seconds: int | None = Field(default=None, ge=1)
    run_at: datetime | None = None
    enabled: bool | None = None


class ReplyJobRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
