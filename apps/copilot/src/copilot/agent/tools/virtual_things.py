from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError

from copilot.virtual_things import DefineVirtualThingRequest, VirtualThingStore


def _thread_id_from_config(config: RunnableConfig) -> str | None:
    value = config.get("configurable", {}).get("thread_id")
    return value if isinstance(value, str) and value else None


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

    try:
        definition = await asyncio.to_thread(VirtualThingStore().define_thing, request)
    except Exception as exc:
        return {"error": str(exc)}
    return {"virtual_thing": definition.model_dump(mode="json", by_alias=True)}


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
