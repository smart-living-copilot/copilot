from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from copilot.virtual_things.builder import (
    VirtualThingBuilder,
    action_definition,
    event_definition,
    event_trigger,
    property_definition,
)
from copilot.virtual_things.dispatcher import VirtualThingDispatcher
from copilot.virtual_things.store import VirtualThingStore


def _thread_id_from_config(config: RunnableConfig) -> str | None:
    value = config.get("configurable", {}).get("thread_id")
    return value if isinstance(value, str) and value else None


@tool
async def create_virtual_thing(
    title: str,
    config: RunnableConfig,
    description: str = "",
    thing_id: str | None = None,
) -> dict[str, Any]:
    """Start a standalone virtual Thing. Returns its thing_id.

    The Thing is created `disabled` and empty. Use the returned thing_id with
    add_virtual_property, add_virtual_action, and add_virtual_event to add its
    affordances one at a time, then call activate_virtual_thing. Calling this
    again with the same thing_id returns the existing Thing unchanged so you can
    keep adding affordances. To start over, delete_virtual_thing first.
    """
    builder = VirtualThingBuilder()
    return await asyncio.to_thread(
        builder.create,
        title=title,
        description=description,
        thing_id=thing_id,
        owner_thread_id=_thread_id_from_config(config),
    )


@tool
async def add_virtual_property(
    thing_id: str,
    name: str,
    handler_code: str,
    value_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add or replace a computed property on a virtual Thing.

    handler_code is Python defining `def handle(input, state, context)` that
    returns the computed value. Read real Things inside handle with the injected
    `wot` client (wot.read_property / wot.invoke_action / wot.write_property);
    capability grants are inferred from literal thing_id/name strings.
    value_schema is an optional JSON Schema for the value and may be omitted.
    """
    builder = VirtualThingBuilder()
    return await asyncio.to_thread(
        builder.add_affordance,
        thing_id=thing_id,
        affordance_type="property",
        affordance_name=name,
        handler_code=handler_code,
        td_definition=property_definition(value_schema),
    )


@tool
async def add_virtual_action(
    thing_id: str,
    name: str,
    handler_code: str,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add or replace a computed action on a virtual Thing.

    handler_code is Python defining `def handle(input, state, context)` that
    returns the result. `input` is the action input. input_schema and
    output_schema are optional JSON Schemas and may be omitted.
    """
    builder = VirtualThingBuilder()
    return await asyncio.to_thread(
        builder.add_affordance,
        thing_id=thing_id,
        affordance_type="action",
        affordance_name=name,
        handler_code=handler_code,
        td_definition=action_definition(input_schema, output_schema),
    )


@tool
async def add_virtual_event(
    thing_id: str,
    name: str,
    handler_code: str,
    interval_seconds: int | None = None,
    source_thing_id: str | None = None,
    source_event_name: str | None = None,
    data_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add or replace an emitted event on a virtual Thing.

    handler_code is Python defining `def handle(input, state, context)` that
    returns {"emit": bool, "payload": value, "state": next_state}. Use `state`
    for threshold or edge detection; initialize it with `state = state or {}`.

    The trigger is set from these arguments:
    - interval_seconds=N evaluates the handler every N seconds.
    - source_thing_id + source_event_name re-evaluates on another Thing's event.
    - omit all three to make the event explicit (fire via emit_virtual_thing_event).
    data_schema is an optional JSON Schema for the payload and may be omitted.
    """
    builder = VirtualThingBuilder()
    return await asyncio.to_thread(
        builder.add_affordance,
        thing_id=thing_id,
        affordance_type="event",
        affordance_name=name,
        handler_code=handler_code,
        td_definition=event_definition(data_schema),
        trigger=event_trigger(interval_seconds, source_thing_id, source_event_name),
    )


@tool
async def activate_virtual_thing(thing_id: str) -> dict[str, Any]:
    """Validate and activate a virtual Thing after its affordances are added.

    Runs a smoke test of every handler and, if it passes, flips the Thing from
    `disabled` to `active`. virtual-servient then produces the concrete catalog
    TD asynchronously. If a smoke test fails, fix the affordance with the
    matching add_virtual_* tool and call this again.
    """
    return await VirtualThingBuilder().activate(thing_id)


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
