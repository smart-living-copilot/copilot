from __future__ import annotations

import ast
import math
from typing import Any

_HANDLER_KEYS = ("handler_code", "handle", "source", "code", "handler")
_DRAFT_META_KEYS = {
    "name",
    "affordance",
    "affordance_name",
    "affordance_type",
    "kind",
    "handler_code",
    "handle",
    "source",
    "code",
    "handler",
    "capabilities",
    "config",
    "timeout_seconds",
    "cache_ttl_seconds",
    "trigger",
    "state",
    "interval_seconds",
    "interval_ms",
    "evaluationInterval",
}


def build_define_args_from_draft(spec: dict[str, Any]) -> dict[str, Any]:
    """Convert a friendly virtual Thing draft into canonical define arguments."""
    if not isinstance(spec, dict):
        raise ValueError("spec must be an object")

    title = _required_string(spec, "title")
    description = _optional_string(spec.get("description"))
    thing_id = _optional_string(spec.get("thing_id") or spec.get("id")) or None
    status = _optional_string(spec.get("status")) or "active"
    td: dict[str, Any] = {"title": title}
    if description:
        td["description"] = description

    bindings: list[dict[str, Any]] = []
    properties = _normalize_affordance_map("properties", spec.get("properties"))
    actions = _normalize_affordance_map("actions", spec.get("actions"))
    events = _normalize_affordance_map("events", spec.get("events"))

    if properties:
        td["properties"] = {}
        for name, raw in properties:
            definition = _td_affordance_definition(raw)
            handler_code = _validated_handler_code("property", name, raw)
            td["properties"][name] = definition
            bindings.append(
                _binding(
                    raw,
                    affordance_type="property",
                    affordance_name=name,
                    kind="computed",
                    handler_code=handler_code,
                )
            )

    if actions:
        td["actions"] = {}
        for name, raw in actions:
            definition = _td_affordance_definition(raw)
            handler_code = _validated_handler_code("action", name, raw)
            td["actions"][name] = definition
            bindings.append(
                _binding(
                    raw,
                    affordance_type="action",
                    affordance_name=name,
                    kind="computed",
                    handler_code=handler_code,
                )
            )

    if events:
        td["events"] = {}
        for name, raw in events:
            definition = _td_affordance_definition(raw)
            handler_code = _validated_handler_code("event", name, raw)
            trigger = _event_trigger(name, raw)
            td["events"][name] = definition
            bindings.append(
                _binding(
                    raw,
                    affordance_type="event",
                    affordance_name=name,
                    kind="emitted",
                    handler_code=handler_code,
                    trigger=trigger,
                )
            )

    if not bindings:
        raise ValueError("spec must define at least one property, action, or event")

    return {
        "title": title,
        "description": description,
        "thing_id": thing_id,
        "status": status,
        "td": td,
        "bindings": bindings,
    }


def _required_string(spec: dict[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _optional_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_affordance_map(section: str, value: Any) -> list[tuple[str, dict[str, Any]]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [
            (_clean_affordance_name(name), _ensure_object(section, raw))
            for name, raw in value.items()
        ]
    if isinstance(value, list):
        normalized: list[tuple[str, dict[str, Any]]] = []
        for raw in value:
            item = _ensure_object(section, raw)
            name = item.get("name") or item.get("affordance_name") or item.get("affordance")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"{section} list entries require a name")
            item = {
                key: val
                for key, val in item.items()
                if key not in {"name", "affordance_name", "affordance"}
            }
            normalized.append((_clean_affordance_name(name), item))
        return normalized
    raise ValueError(f"{section} must be an object or list")


def _clean_affordance_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("affordance names must be non-empty strings")
    return value.strip()


def _ensure_object(section: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{section} entries must be objects")
    return dict(value)


def _td_affordance_definition(raw: dict[str, Any]) -> dict[str, Any]:
    schema = raw.get("schema")
    if isinstance(schema, dict):
        return dict(schema)
    return {key: value for key, value in raw.items() if key not in _DRAFT_META_KEYS}


def _validated_handler_code(affordance_type: str, name: str, raw: dict[str, Any]) -> str:
    handler_code = None
    for key in _HANDLER_KEYS:
        if key in raw:
            handler_code = raw[key]
            break
    if not isinstance(handler_code, str) or not handler_code.strip():
        raise ValueError(f"{affordance_type} {name!r} requires handler_code")

    handler_code = handler_code.strip()
    if _looks_like_javascript(handler_code):
        raise ValueError(
            f"{affordance_type} {name!r} handler_code must be Python code that defines "
            "def handle(input, state, context), not JavaScript"
        )

    try:
        module = ast.parse(handler_code)
    except SyntaxError as exc:
        raise SyntaxError(
            f"{affordance_type} {name!r} handler_code is not valid Python: {exc.msg}"
        ) from exc

    handle_defs = [
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "handle"
    ]
    if not handle_defs:
        raise ValueError(
            f"{affordance_type} {name!r} handler_code must define def handle(input, state, context)"
        )
    args = handle_defs[-1].args
    positional = [arg.arg for arg in args.posonlyargs + args.args]
    if positional != ["input", "state", "context"] or args.vararg or args.kwonlyargs or args.kwarg:
        raise ValueError(
            f"{affordance_type} {name!r} handle signature must be exactly "
            "def handle(input, state, context)"
        )
    return handler_code


def _looks_like_javascript(value: str) -> bool:
    stripped = value.strip()
    return (
        stripped.startswith("function ")
        or stripped.startswith("return {")
        or "=>" in stripped
        or "??" in stripped
        or stripped.endswith("};")
    )


def _event_trigger(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    trigger = raw.get("trigger")
    if isinstance(trigger, dict):
        return dict(trigger)
    if "interval_seconds" in raw:
        return {"kind": "interval", "interval_seconds": raw["interval_seconds"]}
    if "interval_ms" in raw:
        return {
            "kind": "interval",
            "interval_seconds": _milliseconds_to_seconds(raw["interval_ms"]),
        }
    if "evaluationInterval" in raw:
        return {
            "kind": "interval",
            "interval_seconds": _milliseconds_to_seconds(raw["evaluationInterval"]),
        }
    raise ValueError(f"event {name!r} requires trigger")


def _milliseconds_to_seconds(value: Any) -> int:
    if not isinstance(value, (int, float)):
        raise ValueError("interval milliseconds must be a number")
    return max(1, math.ceil(value / 1000))


def _binding(
    raw: dict[str, Any],
    *,
    affordance_type: str,
    affordance_name: str,
    kind: str,
    handler_code: str,
    trigger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    binding: dict[str, Any] = {
        "affordance_type": affordance_type,
        "affordance_name": affordance_name,
        "kind": kind,
        "handler_code": handler_code,
    }
    for key in (
        "capabilities",
        "config",
        "timeout_seconds",
        "cache_ttl_seconds",
        "state",
    ):
        if key in raw:
            binding[key] = raw[key]
    if trigger is not None:
        binding["trigger"] = trigger
    return binding
