from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError

from copilot.virtual_things import DefineVirtualThingRequest, VirtualThingStore
from copilot.virtual_things.dispatcher import VirtualThingDispatcher
from copilot.virtual_things.draft import build_define_args_from_draft
from copilot.virtual_things.validator import VirtualThingValidator


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
        define_args = build_define_args_from_draft(spec)
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


@tool
async def emit_virtual_thing_event(
    thing_id: str,
    event_name: str,
    input: Any = None,
) -> dict[str, Any]:
    """Evaluate and emit a standalone virtual Thing event with an explicit trigger."""
    try:
        return await VirtualThingDispatcher().emit_event(
            thing_id,
            event_name,
            {
                "trigger": "explicit",
                "input": input,
                "requested_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except KeyError:
        return {"error": "virtual thing event not found"}
    except Exception as exc:
        return {"error": str(exc)}
