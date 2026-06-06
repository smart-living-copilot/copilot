from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from copilot.jobs.enums import (
    JobActionKind,
    JobInteractionMode,
    JobOutputKind,
    JobRunEventType,
    JobRunSource,
    JobRunStatus,
    JobTriggerKind,
)
from copilot.jobs.records.ids import make_virtual_record_thing_id
from copilot.jobs.records.schema import validate_record_schema
from copilot.jobs.time_schedule import (
    TimeSchedule,
    initial_next_run_at_for_schedule,
    is_one_shot_schedule,
    next_run_at_for_schedule,
    normalized_time_schedule,
)


class PromptAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["prompt"] = "prompt"
    prompt: str

    @field_validator("prompt")
    @classmethod
    def _prompt_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt jobs require prompt")
        return value


class AnalysisAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["analysis"] = "analysis"
    analysis_code: str

    @field_validator("analysis_code")
    @classmethod
    def _analysis_code_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("analysis jobs require analysis_code")
        return value


JobAction = Annotated[
    PromptAction | AnalysisAction,
    Field(discriminator="kind"),
]


class NarrativeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["narrative"] = "narrative"


class VirtualRecordThing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, max_length=180)
    title: str | None = Field(default=None, max_length=120)
    description: str | None = None


class StructuredRecordOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal["structured_record"] = "structured_record"
    schema_: Any = Field(alias="schema")
    schema_version: int = Field(default=1, ge=1)
    virtual_thing: VirtualRecordThing | None = None

    @field_validator("schema_")
    @classmethod
    def _record_schema_is_valid(cls, value: Any) -> dict[str, Any]:
        return validate_record_schema(value)

    @property
    def schema(self) -> Any:
        return self.schema_

    @property
    def virtual_thing_id(self) -> str | None:
        return self.virtual_thing.id if self.virtual_thing is not None else None


JobOutput = Annotated[
    NarrativeOutput | StructuredRecordOutput,
    Field(discriminator="kind"),
]


class TimeTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["time"] = "time"
    schedule: TimeSchedule


class EventTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["event"] = "event"
    thing_id: str
    event_name: str
    subscription_input: Any | None = None

    @field_validator("thing_id")
    @classmethod
    def _thing_id_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("event jobs require thing_id")
        return value

    @field_validator("event_name")
    @classmethod
    def _event_name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("event jobs require event_name")
        return value


JobTrigger = Annotated[
    TimeTrigger | EventTrigger,
    Field(discriminator="kind"),
]


class JobDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    interaction_mode: JobInteractionMode = JobInteractionMode.AUTONOMOUS
    action: JobAction
    trigger: JobTrigger
    output: JobOutput = Field(default_factory=NarrativeOutput)

    @property
    def action_kind(self) -> JobActionKind:
        return JobActionKind(self.action.kind)

    @property
    def trigger_kind(self) -> JobTriggerKind:
        return JobTriggerKind(self.trigger.kind)

    @property
    def output_kind(self) -> JobOutputKind:
        return JobOutputKind(self.output.kind)

    def normalized(
        self,
        *,
        name: str,
        default_cron_timezone: str,
    ) -> JobDefinition:
        trigger = self.trigger
        if isinstance(trigger, TimeTrigger):
            trigger = trigger.model_copy(
                update={
                    "schedule": normalized_time_schedule(
                        trigger.schedule,
                        default_cron_timezone=default_cron_timezone,
                    )
                }
            )

        output = self.output
        if isinstance(output, StructuredRecordOutput):
            thing = output.virtual_thing or VirtualRecordThing()
            if not thing.id:
                thing = thing.model_copy(
                    update={"id": make_virtual_record_thing_id(thing.title or name)}
                )
            output = output.model_copy(update={"schema_version": output.schema_version or 1})
            output = output.model_copy(update={"virtual_thing": thing})

        return self.model_copy(update={"trigger": trigger, "output": output})

    def next_run_at_after(self, *, now: datetime, enabled: bool = True) -> datetime | None:
        if not isinstance(self.trigger, TimeTrigger):
            return None
        return next_run_at_for_schedule(self.trigger.schedule, now=now, enabled=enabled)

    def initial_next_run_at(self, *, now: datetime, enabled: bool = True) -> datetime | None:
        if not isinstance(self.trigger, TimeTrigger):
            return None
        return initial_next_run_at_for_schedule(self.trigger.schedule, now=now, enabled=enabled)

    def is_one_shot_time_job(self) -> bool:
        return isinstance(self.trigger, TimeTrigger) and is_one_shot_schedule(self.trigger.schedule)


class CreateJobRequest(JobDefinition):
    """Request payload for creating time or event triggered automation jobs."""

    name: str = Field(min_length=1, max_length=120)
    created_from_thread_id: str | None = Field(default=None, max_length=120)

    def normalized_request(self, *, default_cron_timezone: str) -> CreateJobRequest:
        definition = JobDefinition(
            interaction_mode=self.interaction_mode,
            action=self.action,
            trigger=self.trigger,
            output=self.output,
        ).normalized(name=self.name, default_cron_timezone=default_cron_timezone)
        return self.model_copy(
            update={
                "interaction_mode": definition.interaction_mode,
                "action": definition.action,
                "trigger": definition.trigger,
                "output": definition.output,
            }
        )


class Job(JobDefinition):
    """API model for a persisted automation job and its latest run snapshot."""

    id: str
    name: str
    created_from_thread_id: str
    job_thread_id: str
    enabled: bool
    next_run_at: datetime | None = None
    subscription_id: str | None = None
    resource_health: Any | None = None
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

    def normalized_job(self, *, default_cron_timezone: str) -> Job:
        definition = JobDefinition(
            interaction_mode=self.interaction_mode,
            action=self.action,
            trigger=self.trigger,
            output=self.output,
        ).normalized(name=self.name, default_cron_timezone=default_cron_timezone)
        return self.model_copy(
            update={
                "interaction_mode": definition.interaction_mode,
                "action": definition.action,
                "trigger": definition.trigger,
                "output": definition.output,
            }
        )


class JobRun(BaseModel):
    """API model for one execution attempt of a job."""

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


class JobRunEvent(BaseModel):
    """API model for a timeline entry emitted while a job run executes."""

    id: int
    job_id: str
    run_id: str
    event_type: JobRunEventType
    message: str | None = None
    payload: Any | None = None
    created_at: datetime


class UpdateJobRequest(BaseModel):
    """Partial update for a job's metadata and full definition replacement."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    definition: JobDefinition | None = None


class ReplyJobRequest(BaseModel):
    """User reply payload for resuming a job waiting for input."""

    message: str = Field(min_length=1, max_length=8000)
    client_reply_id: str | None = Field(default=None, min_length=1, max_length=120)


def validation_message(exc: ValidationError) -> str:
    for error in exc.errors():
        ctx_error = error.get("ctx", {}).get("error")
        if ctx_error is not None:
            return str(ctx_error)
        message = error.get("msg")
        if isinstance(message, str) and message:
            return message
    return str(exc)
