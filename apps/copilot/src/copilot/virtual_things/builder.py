"""Incremental authoring for standalone virtual Things.

Each affordance is added with its own small tool call instead of submitting a
whole Thing Description in one shot. The Thing is created as a ``disabled`` real
Thing and built up in place; the database is the accumulator (``define_thing``
upserts and replaces bindings), so no separate draft store is required. The
expensive smoke test runs once, at ``activate``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

from copilot.virtual_things.ids import make_virtual_thing_id
from copilot.virtual_things.schemas import (
    DefineVirtualThingRequest,
    VirtualThingDefinition,
)
from copilot.virtual_things.store import VirtualThingStore
from copilot.virtual_things.validator import VirtualThingValidator

_SECTION = {"property": "properties", "action": "actions", "event": "events"}


class VirtualThingBuilder:
    """Create and incrementally extend standalone virtual Thing definitions."""

    def __init__(
        self,
        *,
        store: VirtualThingStore | None = None,
        validator: VirtualThingValidator | None = None,
    ) -> None:
        self._store = store or VirtualThingStore()
        self._validator = validator or VirtualThingValidator()

    def create(
        self,
        *,
        title: str,
        description: str = "",
        thing_id: str | None = None,
        owner_thread_id: str | None = None,
    ) -> dict[str, Any]:
        resolved = thing_id or make_virtual_thing_id(title)
        existing = self._load(resolved)
        if existing is not None:
            return _ok(existing, existing=True)
        try:
            request = DefineVirtualThingRequest(
                id=thing_id,
                title=title,
                description=description,
                td={"title": title},
                bindings=[],
                status="disabled",
                owner_thread_id=owner_thread_id,
            )
        except (ValidationError, ValueError) as exc:
            return {"error": str(exc)}
        return _ok(self._store.define_thing(request))

    def add_affordance(
        self,
        *,
        thing_id: str,
        affordance_type: str,
        affordance_name: str,
        handler_code: str,
        td_definition: dict[str, Any],
        trigger: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self._load(thing_id)
        if current is None:
            return {"error": "virtual thing not found"}

        td = dict(current.td)
        section = _SECTION[affordance_type]
        affordances = dict(td.get(section) or {})
        affordances[affordance_name] = td_definition
        td[section] = affordances

        binding: dict[str, Any] = {
            "affordance_type": affordance_type,
            "affordance_name": affordance_name,
            "kind": "emitted" if affordance_type == "event" else "computed",
            "handler_code": handler_code,
        }
        if trigger is not None:
            binding["trigger"] = trigger
        bindings = _replace_binding(current, affordance_type, affordance_name, binding)

        try:
            request = DefineVirtualThingRequest(
                id=thing_id,
                title=current.title,
                description=current.description,
                td=td,
                bindings=bindings,
                status=current.status,
                owner_thread_id=current.owner_thread_id,
            )
        except (ValidationError, ValueError) as exc:
            return {"error": str(exc)}

        report = self._validator.validate_static(request)
        if not report["ok"]:
            return {"error": "virtual thing static validation failed", "validation_report": report}

        return _ok(self._store.define_thing(request), validation_report=report)

    async def activate(self, thing_id: str) -> dict[str, Any]:
        current = self._load(thing_id)
        if current is None:
            return {"error": "virtual thing not found"}
        if not current.bindings:
            return {"error": "cannot activate a virtual thing with no affordances"}

        try:
            request = DefineVirtualThingRequest(
                id=thing_id,
                title=current.title,
                description=current.description,
                td=dict(current.td),
                bindings=[_binding_dict(binding) for binding in current.bindings],
                status="active",
                owner_thread_id=current.owner_thread_id,
            )
        except (ValidationError, ValueError) as exc:
            return {"error": str(exc)}

        report = await self._validator.validate(request, run_smoke=True)
        if not report["ok"]:
            return {"error": "virtual thing validation failed", "validation_report": report}

        definition = await asyncio.to_thread(self._store.define_thing, request)
        return _ok(definition, validation_report=report)

    def _load(self, thing_id: str) -> VirtualThingDefinition | None:
        try:
            return self._store.get_definition(thing_id, include_disabled=True)
        except KeyError:
            return None


def property_definition(schema: dict[str, Any] | None) -> dict[str, Any]:
    return dict(schema) if isinstance(schema, dict) else {}


def action_definition(
    input_schema: dict[str, Any] | None,
    output_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    definition: dict[str, Any] = {}
    if isinstance(input_schema, dict):
        definition["input"] = dict(input_schema)
    if isinstance(output_schema, dict):
        definition["output"] = dict(output_schema)
    return definition


def event_definition(data_schema: dict[str, Any] | None) -> dict[str, Any]:
    return {"data": dict(data_schema)} if isinstance(data_schema, dict) else {}


def event_trigger(
    interval_seconds: int | None,
    source_thing_id: str | None,
    source_event_name: str | None,
) -> dict[str, Any]:
    if interval_seconds is not None:
        return {"kind": "interval", "interval_seconds": interval_seconds}
    if source_thing_id and source_event_name:
        return {
            "kind": "source_event",
            "thing_id": source_thing_id,
            "event_name": source_event_name,
        }
    return {"kind": "explicit"}


def _replace_binding(
    current: VirtualThingDefinition,
    affordance_type: str,
    affordance_name: str,
    binding: dict[str, Any],
) -> list[dict[str, Any]]:
    bindings = [
        _binding_dict(existing)
        for existing in current.bindings
        if not (
            existing.affordance_type == affordance_type
            and existing.affordance_name == affordance_name
        )
    ]
    bindings.append(binding)
    return bindings


def _binding_dict(binding: Any) -> dict[str, Any]:
    return binding.model_dump(mode="json", exclude_none=True)


def _ok(definition: VirtualThingDefinition, **extra: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "thing_id": definition.id,
        "virtual_thing": definition.model_dump(mode="json", by_alias=True),
        **extra,
    }
