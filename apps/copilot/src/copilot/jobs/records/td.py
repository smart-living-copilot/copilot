from __future__ import annotations

from typing import Any

from copilot.catalog.validation import validate_document
from copilot.jobs.records.schema import safe_affordance_name, scalar_schema_fields


def build_virtual_record_td(
    *,
    thing_id: str,
    title: str,
    description: str,
    record_schema: dict[str, Any],
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "latest_record": _property("Most recent validated record.", {"type": "object"}),
        "record_count": _property("Number of stored records.", {"type": "integer"}),
        "last_recorded_at": _property(
            "Timestamp of the most recent stored record.",
            {"type": "string", "format": "date-time"},
        ),
    }
    history_actions: dict[str, Any] = {}
    for field_name, field_schema in scalar_schema_fields(record_schema).items():
        affordance = safe_affordance_name(field_name)
        properties[f"latest_{affordance}"] = _property(
            f"Most recent value for {field_name}.",
            field_schema,
        )
        history_actions[f"history_{affordance}"] = {
            "description": f"Historical values for {field_name} over a time range.",
            "safe": True,
            "input": _query_input_schema(),
            "output": _history_output_schema(field_schema),
            "forms": [_form(f"history_{affordance}", "invokeaction")],
        }

    td = {
        "@context": "https://www.w3.org/2022/wot/td/v1.1",
        "id": thing_id,
        "title": title,
        "description": description,
        "tags": ["virtual", "records", "generated", "job"],
        "securityDefinitions": {"nosec_sc": {"scheme": "nosec"}},
        "security": "nosec_sc",
        "properties": properties,
        "actions": {
            "query_records": {
                "description": "Query stored records by time range.",
                "safe": True,
                "input": _query_input_schema(),
                "output": _records_output_schema(record_schema),
                "forms": [_form("query_records", "invokeaction")],
            },
            "query_property_history": {
                "description": (
                    "Query historical values for one top-level record property. "
                    "Prefer the per-field history_<field> actions when available."
                ),
                "safe": True,
                "input": _history_input_schema(record_schema),
                "output": _history_output_schema(None),
                "forms": [_form("query_property_history", "invokeaction")],
            },
            **history_actions,
        },
    }
    return validate_document(td)


def _property(description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        **schema,
        "description": description,
        "readOnly": True,
        "forms": [_form("property", "readproperty")],
    }


def _query_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "from": {"type": "string", "format": "date-time"},
            "to": {"type": "string", "format": "date-time"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
        },
    }


def _history_input_schema(record_schema: dict[str, Any]) -> dict[str, Any]:
    base = _query_input_schema()
    field_names = sorted(safe_affordance_name(name) for name in scalar_schema_fields(record_schema))
    property_schema: dict[str, Any] = {
        "type": "string",
        "description": "Top-level record field to return history for.",
    }
    if field_names:
        property_schema["enum"] = field_names
        property_schema["description"] = (
            f"Top-level record field to return history for, e.g. {field_names[0]!r}. "
            "Use the bare field name, not the 'latest_' read-property name."
        )
    return {
        **base,
        "properties": {**base["properties"], "property": property_schema},
        "required": ["property"],
    }


def _records_output_schema(record_schema: dict[str, Any]) -> dict[str, Any]:
    """Mirror VirtualRecordStore._record_payload exactly."""
    data_schema = record_schema if isinstance(record_schema, dict) else {"type": "object"}
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "thing_id": {"type": "string"},
                "schema_version": {"type": "integer"},
                "source_job_id": {"type": "string"},
                "source_run_id": {"type": "string"},
                "recorded_at": {"type": "string", "format": "date-time"},
                "data": data_schema,
                "raw_input": {"oneOf": [{"type": "string"}, {"type": "null"}]},
                "confidence": {"oneOf": [{"type": "number"}, {"type": "null"}]},
            },
            "required": [
                "id",
                "thing_id",
                "schema_version",
                "source_job_id",
                "source_run_id",
                "recorded_at",
                "data",
                "raw_input",
                "confidence",
            ],
        },
    }


def _history_output_schema(value_schema: dict[str, Any] | None) -> dict[str, Any]:
    """Mirror VirtualRecordStore.query_property_history rows exactly.

    value_schema is the field's scalar schema for per-field history actions, or
    None for the generic action where the value type depends on the chosen field.
    """
    value: dict[str, Any] = dict(value_schema) if isinstance(value_schema, dict) else {}
    value["description"] = "Stored field value at recorded_at."
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "recorded_at": {"type": "string", "format": "date-time"},
                "value": value,
                "source_run_id": {"type": "string"},
            },
            "required": ["recorded_at", "value", "source_run_id"],
        },
    }


def _form(path: str, op: str) -> dict[str, Any]:
    return {
        "href": f"urn:smart-living-copilot:virtual-records:{path}",
        "op": [op],
        "contentType": "application/json",
    }
