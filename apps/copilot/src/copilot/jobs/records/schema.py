from __future__ import annotations

import json
import re
from typing import Any

from jsonschema import Draft202012Validator, SchemaError, ValidationError


def validate_record_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        raise ValueError("structured record jobs require record_schema to be an object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"invalid record_schema: {exc.message}") from exc
    if schema.get("type") != "object":
        raise ValueError("record_schema must be a JSON Schema object with type='object'")
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise ValueError("record_schema.properties must be an object")
    return _json_safe(schema)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True, default=str))


def validate_record_data(schema: Any, data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("structured record data must be an object")
    try:
        Draft202012Validator(schema).validate(data)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.path)
        location = f" at {path}" if path else ""
        raise ValueError(f"record data failed schema validation{location}: {exc.message}") from exc


def scalar_schema_fields(record_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    properties = record_schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    fields: dict[str, dict[str, Any]] = {}
    for name, schema in properties.items():
        if not isinstance(name, str) or not isinstance(schema, dict):
            continue
        schema_type = schema.get("type")
        if schema_type in {"string", "integer", "number", "boolean"} or "enum" in schema:
            fields[name] = schema
    return fields


def safe_affordance_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    return value or "value"


def field_name_for_property(record_schema: Any, property_suffix: str) -> str | None:
    properties = record_schema.get("properties") if isinstance(record_schema, dict) else {}
    if not isinstance(properties, dict):
        return None
    for field_name in properties:
        if isinstance(field_name, str) and safe_affordance_name(field_name) == property_suffix:
            return field_name
    return None


def resolve_history_field(record_schema: Any, name: str) -> str | None:
    """Resolve a query_property_history `property` argument to a real schema field.

    Accepts either the bare field affordance name (e.g. "answer") or the
    `latest_`-prefixed read-property name (e.g. "latest_answer"), since the LLM
    routinely passes the property name it sees on the Thing Description.
    """
    direct = field_name_for_property(record_schema, name)
    if direct is not None:
        return direct
    if name.startswith("latest_"):
        return field_name_for_property(record_schema, name.removeprefix("latest_"))
    return None
