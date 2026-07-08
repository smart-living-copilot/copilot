from __future__ import annotations

from enum import StrEnum


class JobTriggerKind(StrEnum):
    """How a job is started."""

    TIME = "time"
    EVENT = "event"


class TimeTriggerKind(StrEnum):
    """Supported schedule shapes for time-triggered jobs."""

    ONCE = "once"
    INTERVAL = "interval"
    CRON = "cron"


class JobActionKind(StrEnum):
    """Runtime implementation used to execute a job."""

    PROMPT = "prompt"
    ANALYSIS = "analysis"


class JobInteractionMode(StrEnum):
    """Whether a prompt job may complete without waiting for the user."""

    AUTONOMOUS = "autonomous"
    REQUIRED_CHECKIN = "required_checkin"


class JobOutputKind(StrEnum):
    """The type of artifact a job is expected to produce."""

    NARRATIVE = "narrative"
    STRUCTURED_RECORD = "structured_record"


class JobRunSource(StrEnum):
    """The trigger source recorded for a specific job run."""

    MANUAL = "manual"
    TIME = "time"
    EVENT = "event"


class JobRunStatus(StrEnum):
    """Lifecycle status for one persisted job execution."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    WAITING_FOR_INPUT = "waiting_for_input"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class JobRunEventType(StrEnum):
    """Timeline event kinds shown for job runs and debugging."""

    RUN_STARTED = "run_started"
    USER_REPLY = "user_reply"
    WAITING_FOR_INPUT = "waiting_for_input"
    ASSISTANT_MESSAGE = "assistant_message"
    RECORD_SUBMITTED = "record_submitted"
    RUN_SUCCEEDED = "run_succeeded"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"
    RUN_SKIPPED = "run_skipped"
