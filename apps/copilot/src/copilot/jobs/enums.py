from __future__ import annotations

from enum import StrEnum


class JobTriggerKind(StrEnum):
    TIME = "time"
    EVENT = "event"


class TimeTriggerKind(StrEnum):
    ONCE = "once"
    INTERVAL = "interval"
    CRON = "cron"


class JobActionKind(StrEnum):
    PROMPT = "prompt"
    ANALYSIS = "analysis"


class JobInteractionMode(StrEnum):
    AUTONOMOUS = "autonomous"
    REQUIRED_CHECKIN = "required_checkin"


class JobOutputKind(StrEnum):
    NARRATIVE = "narrative"
    STRUCTURED_RECORD = "structured_record"


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


class JobRunEventType(StrEnum):
    RUN_STARTED = "run_started"
    USER_REPLY = "user_reply"
    WAITING_FOR_INPUT = "waiting_for_input"
    ASSISTANT_MESSAGE = "assistant_message"
    RECORD_SUBMITTED = "record_submitted"
    RUN_SUCCEEDED = "run_succeeded"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"
    RUN_SKIPPED = "run_skipped"
