from __future__ import annotations

import ast
import asyncio
import math
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError

from copilot.virtual_things import DefineVirtualThingRequest, VirtualThingStore
from copilot.virtual_things.validator import VirtualThingValidator

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


def _thread_id_from_config(config: RunnableConfig) -> str | None:
    value = config.get("configurable", {}).get("thread_id")
    return value if isinstance(value, str) and value else None


@tool
def draft_virtual_thing_definition(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a simplified standalone virtual Thing draft.

    This tool does not persist anything. It converts a friendly authoring spec
    into the canonical arguments for define_virtual_thing:

    {
      "title": "...",
      "description": "...",
      "properties": {"score": {"type": "number", "handler_code": "..."}},
      "actions": {"hello": {"input": {...}, "output": {...}, "handler_code": "..."}},
      "events": {"tick": {"data": {...}, "trigger": {...}, "handler_code": "..."}}
    }

    Handler code must be Python and must define:
    def handle(input, state, context)
    """
    try:
        define_args = _build_define_args(spec)
        request = DefineVirtualThingRequest(
            id=define_args.get("thing_id"),
            title=define_args["title"],
            description=define_args.get("description", ""),
            td=define_args["td"],
            bindings=define_args["bindings"],
            status=define_args.get("status", "active"),
        )
    except (ValidationError, ValueError, SyntaxError) as exc:
        return {"error": str(exc)}

    validation_report = VirtualThingValidator().validate_static(request)
    if not validation_report["ok"]:
        return {
            "error": "virtual thing static validation failed",
            "validation_report": validation_report,
        }

    canonical_args = {
        "title": request.title,
        "description": request.description,
        "status": request.status,
        "thing_id": request.id,
        "td": request.td,
        "bindings": [
            binding.model_dump(mode="json", exclude_none=True) for binding in request.bindings
        ],
    }
    return {
        "ok": True,
        "thing_id": request.id,
        "define_args": canonical_args,
        "validation_report": validation_report,
    }


@tool
async def define_virtual_thing(
    title: str,
    td: dict[str, Any],
    bindings: list[dict[str, Any]],
    config: RunnableConfig,
    thing_id: str | None = None,
    description: str = "",
    status: str = "active",
) -> dict[str, Any]:
    """Create or replace a standalone virtual Thing definition.

    Use this for durable computed WoT capabilities: computed properties,
    computed actions, and emitted events. Submit the whole Thing Description
    affordance schema plus every affordance binding in one call. Binding code
    must define `handle(input, state, context)`.

    For computed properties/actions, return the computed value directly.
    For emitted events, return an object: {"emit": bool, "payload": value,
    "state": next_state}. Returning emit=false suppresses the event; state is
    persisted so handlers can implement threshold or edge detection.
    """
    try:
        request = DefineVirtualThingRequest(
            id=thing_id,
            title=title,
            description=description,
            td=td,
            bindings=bindings,
            status=status,
            owner_thread_id=_thread_id_from_config(config),
        )
    except (ValidationError, ValueError) as exc:
        return {"error": str(exc)}

    validation_report = await VirtualThingValidator().validate(
        request,
        run_smoke=request.status == "active",
    )
    if not validation_report["ok"]:
        return {
            "error": "virtual thing validation failed",
            "validation_report": validation_report,
        }

    try:
        definition = await asyncio.to_thread(VirtualThingStore().define_thing, request)
    except Exception as exc:
        return {"error": str(exc)}
    return {
        "virtual_thing": definition.model_dump(mode="json", by_alias=True),
        "validation_report": validation_report,
    }


@tool
async def delete_virtual_thing(thing_id: str) -> dict[str, Any]:
    """Delete a standalone virtual Thing definition by id."""
    try:
        await asyncio.to_thread(VirtualThingStore().delete_thing, thing_id)
    except KeyError:
        return {"error": "virtual thing not found"}
    except Exception as exc:
        return {"error": str(exc)}
    return {"ok": True, "thing_id": thing_id}


def _build_define_args(spec: dict[str, Any]) -> dict[str, Any]:
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
