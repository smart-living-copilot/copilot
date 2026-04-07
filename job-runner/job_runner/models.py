from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


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
