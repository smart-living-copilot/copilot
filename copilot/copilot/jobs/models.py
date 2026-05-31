from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from copilot.core.orm import Base


class JobRow(Base):
    """SQLAlchemy mapping for the ``jobs`` table (created in core.database.init_db)."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("idx_jobs_due", "trigger_type", "enabled", "next_run_at"),
        Index("idx_jobs_subscription", "subscription_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    job_type: Mapped[str] = mapped_column(Text, nullable=False, default="prompt")
    prompt: Mapped[str | None] = mapped_column(Text)
    analysis_code: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    run_at: Mapped[str | None] = mapped_column(Text)
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    next_run_at: Mapped[str | None] = mapped_column(Text)
    thing_id: Mapped[str | None] = mapped_column(Text)
    event_name: Mapped[str | None] = mapped_column(Text)
    subscription_id: Mapped[str | None] = mapped_column(Text)
    subscription_input_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_run_at: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_response: Mapped[str | None] = mapped_column(Text)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_fetch_value: Mapped[str | None] = mapped_column(Text)


class Job(BaseModel):
    id: str
    name: str
    thread_id: str
    job_type: Literal["prompt", "analysis"] = "prompt"
    prompt: str | None = None
    analysis_code: str | None = None
    enabled: bool
    trigger_type: Literal["time", "event"]
    run_at: datetime | None = None
    interval_seconds: int | None = None
    next_run_at: datetime | None = None
    thing_id: str | None = None
    event_name: str | None = None
    subscription_id: str | None = None
    subscription_input: Any | None = None
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    last_error: str | None = None
    last_response: str | None = None
    run_count: int = 0
    last_fetch_value: str | None = None


class CreateJobRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    thread_id: str = Field(min_length=1, max_length=120)
    job_type: Literal["prompt", "analysis"] = "prompt"
    prompt: str | None = None
    analysis_code: str | None = None
    trigger_type: Literal["time", "event"]

    run_at: datetime | None = None
    interval_seconds: int | None = Field(default=None, ge=1)

    thing_id: str | None = None
    event_name: str | None = None
    subscription_input: Any | None = None
