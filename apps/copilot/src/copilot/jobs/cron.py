from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pycron

DEFAULT_CRON_TIMEZONE = "UTC"
CRON_LOOKAHEAD_MINUTES = 5 * 366 * 24 * 60


class CronScheduleError(ValueError):
    """Raised when a cron expression or timezone cannot produce a next run."""


def normalize_cron_expression(value: str | None) -> str:
    expression = " ".join((value or "").strip().split())
    if not expression:
        raise CronScheduleError("cron jobs require cron_expression")
    parts = expression.split(" ")
    if len(parts) != 5:
        raise CronScheduleError(
            "cron_expression must use five fields: minute hour day month weekday"
        )
    return expression


def normalize_cron_timezone(value: str | None, *, default: str = DEFAULT_CRON_TIMEZONE) -> str:
    timezone_name = (value or default).strip() or default
    try:
        ZoneInfo(timezone_name)
    except Exception as exc:
        raise CronScheduleError(f"Unknown cron_timezone: {timezone_name}") from exc
    return timezone_name


def next_cron_run_at(
    expression: str | None,
    timezone_name: str | None,
    *,
    after: datetime | None = None,
) -> datetime:
    cron_expression = normalize_cron_expression(expression)
    cron_timezone = normalize_cron_timezone(timezone_name)
    zone = ZoneInfo(cron_timezone)
    after_utc = _as_utc(after or datetime.now(timezone.utc))
    candidate = (
        after_utc.astimezone(zone).replace(second=0, microsecond=0)
        + timedelta(minutes=1)
    )

    for _ in range(CRON_LOOKAHEAD_MINUTES):
        if _cron_matches(cron_expression, candidate):
            return candidate.astimezone(timezone.utc)
        candidate += timedelta(minutes=1)

    raise CronScheduleError(
        f"cron_expression does not produce a run within five years: {cron_expression}"
    )


def validate_cron_schedule(
    expression: str | None,
    timezone_name: str | None,
    *,
    after: datetime | None = None,
) -> tuple[str, str]:
    cron_expression = normalize_cron_expression(expression)
    cron_timezone = normalize_cron_timezone(timezone_name)
    next_cron_run_at(cron_expression, cron_timezone, after=after)
    return cron_expression, cron_timezone


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cron_matches(expression: str, candidate: datetime) -> bool:
    try:
        return pycron.is_now(expression, candidate)
    except (ValueError, ZeroDivisionError) as exc:
        raise CronScheduleError(str(exc)) from exc
