from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from copilot.jobs.enums import (
    JobActionKind,
    JobInteractionMode,
    JobOutputKind,
    JobTriggerKind,
)
from copilot.jobs.records import make_virtual_record_thing_id, validate_record_schema
from copilot.jobs.schemas import CreateJobRequest, Job
from copilot.jobs.time_schedule import TimeSchedule, normalize_time_schedule_update
from copilot.jobs.time_schedule import time_schedule_from_flat


class PromptAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_kind: Literal[JobActionKind.PROMPT] = JobActionKind.PROMPT
    prompt: str

    @field_validator("prompt")
    @classmethod
    def _prompt_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt jobs require prompt")
        return value


class AnalysisAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_kind: Literal[JobActionKind.ANALYSIS] = JobActionKind.ANALYSIS
    analysis_code: str

    @field_validator("analysis_code")
    @classmethod
    def _analysis_code_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("analysis jobs require analysis_code")
        return value


JobAction = Annotated[
    PromptAction | AnalysisAction,
    Field(discriminator="action_kind"),
]


class NarrativeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_kind: Literal[JobOutputKind.NARRATIVE] = JobOutputKind.NARRATIVE


class StructuredRecordOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_kind: Literal[JobOutputKind.STRUCTURED_RECORD] = JobOutputKind.STRUCTURED_RECORD
    record_schema: Any
    record_schema_version: int = 1
    virtual_thing_id: str

    @field_validator("record_schema")
    @classmethod
    def _record_schema_is_valid(cls, value: Any) -> dict[str, Any]:
        return validate_record_schema(value)

    @field_validator("virtual_thing_id")
    @classmethod
    def _virtual_thing_id_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("structured record jobs require virtual_thing_id")
        return value

    def to_flat_fields(self) -> dict[str, Any]:
        return {
            "record_schema": self.record_schema,
            "record_schema_version": self.record_schema_version,
            "virtual_thing_id": self.virtual_thing_id,
        }


JobOutput = Annotated[
    NarrativeOutput | StructuredRecordOutput,
    Field(discriminator="output_kind"),
]


class TimeTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger_kind: Literal[JobTriggerKind.TIME] = JobTriggerKind.TIME
    schedule: TimeSchedule


class EventTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger_kind: Literal[JobTriggerKind.EVENT] = JobTriggerKind.EVENT
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
    Field(discriminator="trigger_kind"),
]


class JobDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    trigger: JobTrigger
    action: JobAction
    output: JobOutput
    interaction_mode: JobInteractionMode

    @model_validator(mode="after")
    def _analysis_records_are_deferred(self) -> JobDefinition:
        if isinstance(self.action, AnalysisAction) and isinstance(
            self.output,
            StructuredRecordOutput,
        ):
            raise ValueError("analysis jobs only support narrative output")
        return self

    def normalized_create_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if isinstance(self.trigger, TimeTrigger):
            fields.update(self.trigger.schedule.to_flat_fields())
        if isinstance(self.output, StructuredRecordOutput):
            fields.update(self.output.to_flat_fields())
        return fields


def normalize_create_request(
    request: CreateJobRequest,
    *,
    default_cron_timezone: str,
) -> CreateJobRequest:
    definition = job_definition_from_create_request(
        request,
        default_cron_timezone=default_cron_timezone,
    )
    updates = definition.normalized_create_fields()
    return request.model_copy(update=updates) if updates else request


def normalize_update_fields(
    job: Job,
    fields: dict[str, Any],
    *,
    default_cron_timezone: str,
) -> dict[str, Any]:
    if "prompt" in fields and job.action_kind != JobActionKind.PROMPT:
        raise ValueError("prompt can only be set on prompt jobs")
    if "analysis_code" in fields and job.action_kind != JobActionKind.ANALYSIS:
        raise ValueError("analysis_code can only be set on analysis jobs")

    normalized = normalize_time_schedule_update(
        job,
        fields,
        default_cron_timezone=default_cron_timezone,
    )
    candidate = job.model_copy(update=normalized)
    job_definition_from_job(candidate, default_cron_timezone=default_cron_timezone)
    return normalized


def job_definition_from_create_request(
    request: CreateJobRequest,
    *,
    default_cron_timezone: str,
) -> JobDefinition:
    return _job_definition_from_flat_source(
        request,
        default_cron_timezone=default_cron_timezone,
        generate_missing_virtual_thing_id=True,
    )


def job_definition_from_job(
    job: Job,
    *,
    default_cron_timezone: str,
) -> JobDefinition:
    return _job_definition_from_flat_source(
        job,
        default_cron_timezone=default_cron_timezone,
        generate_missing_virtual_thing_id=False,
    )


def _job_definition_from_flat_source(
    source: CreateJobRequest | Job,
    *,
    default_cron_timezone: str,
    generate_missing_virtual_thing_id: bool,
) -> JobDefinition:
    try:
        return JobDefinition(
            trigger=_trigger_from_flat_source(source, default_cron_timezone),
            action=_action_from_flat(
                action_kind=source.action_kind,
                prompt=source.prompt,
                analysis_code=source.analysis_code,
            ),
            output=_output_from_flat(
                output_kind=source.output_kind,
                name=source.name,
                record_schema=source.record_schema,
                record_schema_version=source.record_schema_version,
                virtual_thing_id=source.virtual_thing_id,
                virtual_thing_title=getattr(source, "virtual_thing_title", None),
                virtual_thing_description=getattr(
                    source,
                    "virtual_thing_description",
                    None,
                ),
                generate_missing_virtual_thing_id=generate_missing_virtual_thing_id,
            ),
            interaction_mode=source.interaction_mode,
        )
    except ValidationError as exc:
        raise ValueError(_validation_message(exc)) from exc


def _action_from_flat(
    *,
    action_kind: JobActionKind,
    prompt: str | None,
    analysis_code: str | None,
) -> JobAction:
    if action_kind == JobActionKind.ANALYSIS:
        return AnalysisAction(analysis_code=analysis_code or "")
    return PromptAction(prompt=prompt or "")


def _output_from_flat(
    *,
    output_kind: JobOutputKind,
    name: str,
    record_schema: Any | None,
    record_schema_version: int | None,
    virtual_thing_id: str | None,
    virtual_thing_title: str | None,
    virtual_thing_description: str | None,
    generate_missing_virtual_thing_id: bool,
) -> JobOutput:
    if output_kind == JobOutputKind.STRUCTURED_RECORD:
        thing_id = virtual_thing_id
        if not thing_id and generate_missing_virtual_thing_id:
            thing_id = make_virtual_record_thing_id(virtual_thing_title or name)
        return StructuredRecordOutput(
            record_schema=record_schema,
            record_schema_version=record_schema_version or 1,
            virtual_thing_id=thing_id or "",
        )

    if (
        record_schema is not None
        or record_schema_version is not None
        or virtual_thing_id is not None
        or virtual_thing_title is not None
        or virtual_thing_description is not None
    ):
        raise ValueError("record fields require output_kind='structured_record'")
    return NarrativeOutput()


def _trigger_from_flat_source(
    source: CreateJobRequest | Job,
    default_cron_timezone: str,
) -> JobTrigger:
    if source.trigger_kind == JobTriggerKind.TIME:
        return TimeTrigger(
            schedule=time_schedule_from_flat(
                schedule_kind=source.schedule_kind,
                run_at=source.run_at,
                interval_seconds=source.interval_seconds,
                cron_expression=source.cron_expression,
                cron_timezone=source.cron_timezone,
                default_cron_timezone=default_cron_timezone,
            )
        )

    _reject_time_schedule_fields(source)
    return EventTrigger(
        thing_id=source.thing_id or "",
        event_name=source.event_name or "",
        subscription_input=source.subscription_input,
    )


def _reject_time_schedule_fields(source: CreateJobRequest | Job) -> None:
    if (
        source.schedule_kind is not None
        or source.run_at is not None
        or source.interval_seconds is not None
        or source.cron_expression is not None
        or source.cron_timezone is not None
    ):
        raise ValueError("event jobs cannot include time schedule fields")


def _validation_message(exc: ValidationError) -> str:
    for error in exc.errors():
        ctx_error = error.get("ctx", {}).get("error")
        if ctx_error is not None:
            return str(ctx_error)
        message = error.get("msg")
        if isinstance(message, str) and message:
            return message
    return str(exc)
