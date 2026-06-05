from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from copilot.jobs.cron import DEFAULT_CRON_TIMEZONE, next_cron_run_at, validate_cron_schedule
from copilot.jobs.enums import JobTriggerKind, TimeTriggerKind
from copilot.jobs.schemas import CreateJobRequest, Job


SCHEDULE_FIELD_NAMES = frozenset(
    {
        "schedule_kind",
        "interval_seconds",
        "run_at",
        "cron_expression",
        "cron_timezone",
    }
)


class _TimeScheduleBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_kind: TimeTriggerKind

    def next_after(self, now: datetime) -> datetime | None:
        raise NotImplementedError

    def initial_next_run_at(self, now: datetime) -> datetime | None:
        return self.next_after(now)

    def to_flat_fields(self) -> dict[str, Any]:
        raise NotImplementedError


class OnceSchedule(_TimeScheduleBase):
    schedule_kind: Literal[TimeTriggerKind.ONCE] = TimeTriggerKind.ONCE
    run_at: datetime

    def next_after(self, now: datetime) -> datetime | None:
        run_at = _as_utc(self.run_at)
        return run_at if run_at > _as_utc(now) else None

    def initial_next_run_at(self, now: datetime) -> datetime | None:
        return self.run_at

    def to_flat_fields(self) -> dict[str, Any]:
        return {
            "schedule_kind": TimeTriggerKind.ONCE,
            "run_at": self.run_at,
            "interval_seconds": None,
            "cron_expression": None,
            "cron_timezone": None,
        }


class IntervalSchedule(_TimeScheduleBase):
    schedule_kind: Literal[TimeTriggerKind.INTERVAL] = TimeTriggerKind.INTERVAL
    interval_seconds: int

    def next_after(self, now: datetime) -> datetime | None:
        return _as_utc(now) + timedelta(seconds=self.interval_seconds)

    def to_flat_fields(self) -> dict[str, Any]:
        return {
            "schedule_kind": TimeTriggerKind.INTERVAL,
            "run_at": None,
            "interval_seconds": self.interval_seconds,
            "cron_expression": None,
            "cron_timezone": None,
        }


class CronSchedule(_TimeScheduleBase):
    schedule_kind: Literal[TimeTriggerKind.CRON] = TimeTriggerKind.CRON
    cron_expression: str
    cron_timezone: str

    def next_after(self, now: datetime) -> datetime | None:
        return next_cron_run_at(
            self.cron_expression,
            self.cron_timezone,
            after=_as_utc(now),
        )

    def to_flat_fields(self) -> dict[str, Any]:
        return {
            "schedule_kind": TimeTriggerKind.CRON,
            "run_at": None,
            "interval_seconds": None,
            "cron_expression": self.cron_expression,
            "cron_timezone": self.cron_timezone,
        }


TimeSchedule = Annotated[
    OnceSchedule | IntervalSchedule | CronSchedule,
    Field(discriminator="schedule_kind"),
]


def time_schedule_from_flat(
    *,
    schedule_kind: TimeTriggerKind | str | None,
    run_at: datetime | None,
    interval_seconds: int | None,
    cron_expression: str | None,
    cron_timezone: str | None,
    default_cron_timezone: str = DEFAULT_CRON_TIMEZONE,
) -> TimeSchedule:
    kind = _schedule_kind(schedule_kind)
    if kind is None:
        raise ValueError("time jobs require schedule_kind")

    if kind == TimeTriggerKind.ONCE:
        if (
            run_at is None
            or interval_seconds is not None
            or cron_expression is not None
            or cron_timezone is not None
        ):
            raise ValueError("one-time jobs require run_at only")
        return OnceSchedule(run_at=run_at)

    if kind == TimeTriggerKind.INTERVAL:
        if (
            interval_seconds is None
            or run_at is not None
            or cron_expression is not None
            or cron_timezone is not None
        ):
            raise ValueError("interval jobs require interval_seconds only")
        return IntervalSchedule(interval_seconds=interval_seconds)

    if kind == TimeTriggerKind.CRON:
        if cron_expression is None or run_at is not None or interval_seconds is not None:
            raise ValueError("cron jobs require cron_expression only")
        expression, timezone_name = validate_cron_schedule(
            cron_expression,
            cron_timezone or default_cron_timezone,
        )
        return CronSchedule(
            cron_expression=expression,
            cron_timezone=timezone_name,
        )

    raise ValueError(f"Unsupported schedule_kind: {schedule_kind}")


def time_schedule_from_request(
    request: CreateJobRequest,
    *,
    default_cron_timezone: str = DEFAULT_CRON_TIMEZONE,
) -> TimeSchedule:
    if request.trigger_kind != JobTriggerKind.TIME:
        raise ValueError("time schedule requires trigger_kind='time'")
    return time_schedule_from_flat(
        schedule_kind=request.schedule_kind,
        run_at=request.run_at,
        interval_seconds=request.interval_seconds,
        cron_expression=request.cron_expression,
        cron_timezone=request.cron_timezone,
        default_cron_timezone=default_cron_timezone,
    )


def time_schedule_from_job(
    job: Job,
    *,
    default_cron_timezone: str = DEFAULT_CRON_TIMEZONE,
) -> TimeSchedule:
    if job.trigger_kind != JobTriggerKind.TIME:
        raise ValueError("time schedule requires trigger_kind='time'")
    return time_schedule_from_flat(
        schedule_kind=job.schedule_kind,
        run_at=job.run_at,
        interval_seconds=job.interval_seconds,
        cron_expression=job.cron_expression,
        cron_timezone=job.cron_timezone,
        default_cron_timezone=default_cron_timezone,
    )


def normalize_time_schedule_update(
    job: Any,
    fields: dict[str, Any],
    *,
    default_cron_timezone: str = DEFAULT_CRON_TIMEZONE,
) -> dict[str, Any]:
    if not SCHEDULE_FIELD_NAMES.intersection(fields):
        return fields
    if job.trigger_kind != JobTriggerKind.TIME:
        raise ValueError("schedule fields can only be set on time jobs")

    old_kind = job.schedule_kind
    new_kind = fields.get("schedule_kind", old_kind)
    kind_changed = "schedule_kind" in fields and new_kind != old_kind

    def merged(name: str) -> Any:
        if name in fields:
            return fields[name]
        if kind_changed:
            return None
        return getattr(job, name)

    schedule = time_schedule_from_flat(
        schedule_kind=new_kind,
        run_at=merged("run_at"),
        interval_seconds=merged("interval_seconds"),
        cron_expression=merged("cron_expression"),
        cron_timezone=merged("cron_timezone"),
        default_cron_timezone=default_cron_timezone,
    )

    normalized = dict(fields)
    if "schedule_kind" in fields:
        normalized.update(schedule.to_flat_fields())
    elif schedule.schedule_kind == TimeTriggerKind.CRON:
        normalized["cron_expression"] = schedule.cron_expression
        normalized["cron_timezone"] = schedule.cron_timezone
    return normalized


def next_run_at_for_job(
    job: Job,
    *,
    now: datetime,
    default_cron_timezone: str = DEFAULT_CRON_TIMEZONE,
) -> datetime | None:
    if job.trigger_kind != JobTriggerKind.TIME or not job.enabled:
        return None
    return time_schedule_from_job(
        job,
        default_cron_timezone=default_cron_timezone,
    ).next_after(now)


def next_run_at_after_time_run(
    job: Job,
    *,
    now: datetime,
    default_cron_timezone: str = DEFAULT_CRON_TIMEZONE,
) -> datetime | None:
    return next_run_at_for_job(
        job,
        now=now,
        default_cron_timezone=default_cron_timezone,
    )


def initial_next_run_at_for_request(
    request: CreateJobRequest,
    *,
    now: datetime,
    default_cron_timezone: str = DEFAULT_CRON_TIMEZONE,
) -> datetime | None:
    if request.trigger_kind != JobTriggerKind.TIME:
        return None
    return time_schedule_from_request(
        request,
        default_cron_timezone=default_cron_timezone,
    ).initial_next_run_at(now)


def is_one_shot_time_job(job: Job) -> bool:
    return job.trigger_kind == JobTriggerKind.TIME and job.schedule_kind == TimeTriggerKind.ONCE


def _schedule_kind(value: TimeTriggerKind | str | None) -> TimeTriggerKind | None:
    if value is None:
        return None
    return value if isinstance(value, TimeTriggerKind) else TimeTriggerKind(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
