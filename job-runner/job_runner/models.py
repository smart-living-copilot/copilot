from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Job(BaseModel):
    id: str
    name: str
    thread_id: str
    prompt: str
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


class CreateJobRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    thread_id: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1)
    trigger_type: Literal["time", "event"]

    run_at: datetime | None = None
    interval_seconds: int | None = Field(default=None, ge=1)

    thing_id: str | None = None
    event_name: str | None = None
    subscription_input: Any | None = None


class DispatchPayload(BaseModel):
    thread_id: str
    prompt: str
    metadata: dict[str, Any] = Field(default_factory=dict)
