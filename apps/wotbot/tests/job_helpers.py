from __future__ import annotations

from typing import Any

from wotbot.jobs.models import (
    CreateJobRequest,
    JobActionKind,
    JobOutputKind,
    JobTriggerKind,
    TimeTriggerKind,
)


def create_job_request(**values: Any) -> CreateJobRequest:
    if "action" in values and "trigger" in values:
        return CreateJobRequest(**values)

    action_kind = values.pop("action_kind", JobActionKind.PROMPT)
    prompt = values.pop("prompt", None)
    analysis_code = values.pop("analysis_code", None)
    output_kind = values.pop("output_kind", JobOutputKind.NARRATIVE)
    trigger_kind = values.pop("trigger_kind")
    schedule_kind = values.pop("schedule_kind", None)
    run_at = values.pop("run_at", None)
    interval_seconds = values.pop("interval_seconds", None)
    cron_expression = values.pop("cron_expression", None)
    cron_timezone = values.pop("cron_timezone", None)
    thing_id = values.pop("thing_id", None)
    event_name = values.pop("event_name", None)
    subscription_input = values.pop("subscription_input", None)
    record_schema = values.pop("record_schema", None)
    record_schema_version = values.pop("record_schema_version", None)
    virtual_thing_id = values.pop("virtual_thing_id", None)
    virtual_thing_title = values.pop("virtual_thing_title", None)
    virtual_thing_description = values.pop("virtual_thing_description", None)

    if action_kind == JobActionKind.ANALYSIS:
        values["action"] = {"kind": "analysis", "analysis_code": analysis_code or ""}
    else:
        values["action"] = {"kind": "prompt", "prompt": prompt or ""}

    if trigger_kind == JobTriggerKind.EVENT:
        values["trigger"] = {
            "kind": "event",
            "thing_id": thing_id,
            "event_name": event_name,
            "subscription_input": subscription_input,
        }
    elif schedule_kind == TimeTriggerKind.ONCE:
        values["trigger"] = {"kind": "time", "schedule": {"kind": "once", "run_at": run_at}}
    elif schedule_kind == TimeTriggerKind.CRON:
        values["trigger"] = {
            "kind": "time",
            "schedule": {
                "kind": "cron",
                "expression": cron_expression,
                "timezone": cron_timezone,
            },
        }
    else:
        values["trigger"] = {
            "kind": "time",
            "schedule": {"kind": "interval", "interval_seconds": interval_seconds},
        }

    if output_kind == JobOutputKind.STRUCTURED_RECORD:
        values["output"] = {
            "kind": "structured_record",
            "schema": record_schema,
            "schema_version": record_schema_version or 1,
            "virtual_thing": {
                "id": virtual_thing_id,
                "title": virtual_thing_title,
                "description": virtual_thing_description,
            },
        }
    else:
        values["output"] = {"kind": "narrative"}

    return CreateJobRequest(**values)
