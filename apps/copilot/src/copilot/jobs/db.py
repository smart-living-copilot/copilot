from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from copilot.core.orm import Base
from copilot.jobs.enums import JobActionKind, JobInteractionMode, JobOutputKind


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
            "interaction_mode IN ('autonomous', 'required_checkin')",
            name="ck_jobs_interaction_mode",
        ),
        CheckConstraint(
            "output_kind IN ('narrative', 'structured_record')",
            name="ck_jobs_output_kind",
        ),
        CheckConstraint(
            "schedule_kind IS NULL OR schedule_kind IN ('once', 'interval', 'cron')",
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
    interaction_mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=JobInteractionMode.AUTONOMOUS.value,
    )
    output_kind: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=JobOutputKind.NARRATIVE.value,
    )
    prompt: Mapped[str | None] = mapped_column(Text)
    analysis_code: Mapped[str | None] = mapped_column(Text)
    record_schema: Mapped[Any | None] = mapped_column(JSONB)
    record_schema_version: Mapped[int | None] = mapped_column(Integer)
    virtual_thing_id: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_kind: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_kind: Mapped[str | None] = mapped_column(Text)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    cron_expression: Mapped[str | None] = mapped_column(Text)
    cron_timezone: Mapped[str | None] = mapped_column(Text)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    thing_id: Mapped[str | None] = mapped_column(Text)
    event_name: Mapped[str | None] = mapped_column(Text)
    subscription_id: Mapped[str | None] = mapped_column(Text)
    subscription_input: Mapped[Any | None] = mapped_column(JSONB)
    resource_health: Mapped[Any | None] = mapped_column(JSONB)
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


class JobRunEventRecord(Base):
    """Canonical user/debug timeline for a job run."""

    __tablename__ = "job_run_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'run_started', "
            "'user_reply', "
            "'waiting_for_input', "
            "'assistant_message', "
            "'record_submitted', "
            "'run_succeeded', "
            "'run_failed', "
            "'run_cancelled', "
            "'run_skipped'"
            ")",
            name="ck_job_run_events_type",
        ),
        Index("idx_job_run_events_job_created", "job_id", "created_at", "id"),
        Index("idx_job_run_events_run_created", "run_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    job_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("job_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
