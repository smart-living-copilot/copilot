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
    for field_name, field_schema in scalar_schema_fields(record_schema).items():
        properties[f"latest_{safe_affordance_name(field_name)}"] = _property(
            f"Most recent value for {field_name}.",
            field_schema,
        )

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
                "output": {"type": "array", "items": {"type": "object"}},
                "forms": [_form("query_records", "invokeaction")],
            },
            "query_property_history": {
                "description": "Query historical values for one top-level record property.",
                "safe": True,
                "input": {
                    **_query_input_schema(),
                    "required": ["property"],
                },
                "output": {"type": "array", "items": {"type": "object"}},
                "forms": [_form("query_property_history", "invokeaction")],
            },
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


def _form(path: str, op: str) -> dict[str, Any]:
    return {
        "href": f"urn:smart-living-copilot:virtual-records:{path}",
        "op": [op],
        "contentType": "application/json",
    }
