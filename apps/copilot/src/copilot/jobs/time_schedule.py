from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from copilot.jobs.cron import DEFAULT_CRON_TIMEZONE, next_cron_run_at, validate_cron_schedule


class _TimeScheduleBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str

    def next_after(self, now: datetime) -> datetime | None:
        raise NotImplementedError

    def initial_next_run_at(self, now: datetime) -> datetime | None:
        return self.next_after(now)


class OnceSchedule(_TimeScheduleBase):
    kind: Literal["once"] = "once"
    run_at: datetime

    def next_after(self, now: datetime) -> datetime | None:
        run_at = _as_utc(self.run_at)
        return run_at if run_at > _as_utc(now) else None

    def initial_next_run_at(self, now: datetime) -> datetime | None:
        return self.run_at


class IntervalSchedule(_TimeScheduleBase):
    kind: Literal["interval"] = "interval"
    interval_seconds: int = Field(ge=1)

    def next_after(self, now: datetime) -> datetime | None:
        return _as_utc(now) + timedelta(seconds=self.interval_seconds)


class CronSchedule(_TimeScheduleBase):
    kind: Literal["cron"] = "cron"
    expression: str = Field(max_length=120)
    timezone: str | None = Field(default=None, max_length=80)

    @field_validator("expression")
    @classmethod
    def _expression_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cron jobs require expression")
        return value.strip()

    @field_validator("timezone")
    @classmethod
    def _timezone_is_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    def normalized(self, *, default_timezone: str = DEFAULT_CRON_TIMEZONE) -> CronSchedule:
        expression, timezone_name = validate_cron_schedule(
            self.expression,
            self.timezone or default_timezone,
        )
        return self.model_copy(update={"expression": expression, "timezone": timezone_name})

    def next_after(self, now: datetime) -> datetime | None:
        schedule = self.normalized()
        return next_cron_run_at(
            schedule.expression,
            schedule.timezone or DEFAULT_CRON_TIMEZONE,
            after=_as_utc(now),
        )


TimeSchedule = Annotated[
    OnceSchedule | IntervalSchedule | CronSchedule,
    Field(discriminator="kind"),
]


def normalized_time_schedule(
    schedule: TimeSchedule,
    *,
    default_cron_timezone: str = DEFAULT_CRON_TIMEZONE,
) -> TimeSchedule:
    if isinstance(schedule, CronSchedule):
        return schedule.normalized(default_timezone=default_cron_timezone)
    return schedule


def next_run_at_for_schedule(
    schedule: TimeSchedule,
    *,
    now: datetime,
    enabled: bool = True,
) -> datetime | None:
    return schedule.next_after(now) if enabled else None


def initial_next_run_at_for_schedule(
    schedule: TimeSchedule,
    *,
    now: datetime,
    enabled: bool = True,
) -> datetime | None:
    return schedule.initial_next_run_at(now) if enabled else None


def is_one_shot_schedule(schedule: TimeSchedule) -> bool:
    return isinstance(schedule, OnceSchedule)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
