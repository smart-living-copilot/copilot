from __future__ import annotations

from typing import Any

from copilot.clients.code_executor import CodeExecutorClient
from copilot.core.settings import Settings
from copilot.jobs.records import VirtualRecordStore
from copilot.virtual_things.cache import get_cached_value, set_cached_value
from copilot.virtual_things.handler import RESULT_PREFIX, VirtualThingHandlerRunner
from copilot.virtual_things.store import VirtualThingStore

_RESULT_PREFIX = RESULT_PREFIX


class VirtualThingDispatcher:
    """Dispatches virtual affordance interactions by binding kind."""

    def __init__(
        self,
        *,
        store: VirtualThingStore | None = None,
        record_store: VirtualRecordStore | None = None,
        code_executor: CodeExecutorClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._store = store or VirtualThingStore()
        self._record_store = record_store or VirtualRecordStore()
        self._settings = settings or Settings()
        self._code_executor = code_executor or CodeExecutorClient(self._settings)
        self._handler_runner = VirtualThingHandlerRunner(self._code_executor)

    async def read_property(self, thing_id: str, property_name: str) -> Any:
        binding = self._store.get_binding(
            thing_id=thing_id,
            affordance_type="property",
            affordance_name=property_name,
        )
        if binding.kind == "record":
            return self._record_store.read_property(thing_id, property_name)
        if binding.kind != "computed":
            raise KeyError(property_name)

        cache_key = f"{thing_id}:property:{property_name}"
        cached = get_cached_value(cache_key)
        if cached.found:
            return cached.value

        value = await self._handler_runner.run_handler(
            binding,
            input_value=None,
            state=binding.state,
        )
        if binding.cache_ttl_seconds > 0:
            set_cached_value(cache_key, value, binding.cache_ttl_seconds)
        return value

    async def invoke_action(self, thing_id: str, action_name: str, input_data: Any) -> Any:
        binding = self._store.get_binding(
            thing_id=thing_id,
            affordance_type="action",
            affordance_name=action_name,
        )
        if binding.kind == "record":
            return self._record_store.invoke_action(thing_id, action_name, input_data)
        if binding.kind != "computed":
            raise KeyError(action_name)
        return await self._handler_runner.run_handler(
            binding,
            input_value=input_data,
            state=binding.state,
        )

    async def evaluate_event(
        self,
        thing_id: str,
        event_name: str,
        trigger_input: Any,
        *,
        dry_run: bool = False,
    ) -> Any | None:
        result = await self._evaluate_event_result(
            thing_id,
            event_name,
            trigger_input,
            dry_run=dry_run,
        )
        return result["payload"] if result["emitted"] else None

    async def emit_event(
        self,
        thing_id: str,
        event_name: str,
        trigger_input: Any,
    ) -> dict[str, Any]:
        result = await self._evaluate_event_result(
            thing_id,
            event_name,
            trigger_input,
            dry_run=False,
        )
        if result["emitted"]:
            self._store.enqueue_event_emission(
                thing_id=thing_id,
                event_name=event_name,
                payload=result.get("payload"),
            )
        return result

    async def _evaluate_event_result(
        self,
        thing_id: str,
        event_name: str,
        trigger_input: Any,
        *,
        dry_run: bool,
    ) -> dict[str, Any]:
        binding = self._store.get_binding(
            thing_id=thing_id,
            affordance_type="event",
            affordance_name=event_name,
        )
        if binding.kind != "emitted":
            raise KeyError(event_name)
        result = await self._handler_runner.run_handler(
            binding,
            input_value=trigger_input,
            state=binding.state,
        )
        _validate_event_result(event_name, result)
        if not dry_run:
            self._store.update_binding_state(binding_id=binding.id, state=result.get("state"))
        emitted = result["emit"]
        return {
            "thing_id": thing_id,
            "event_name": event_name,
            "emitted": emitted,
            "payload": result.get("payload") if emitted else None,
        }


def _validate_event_result(event_name: str, result: Any) -> None:
    if result is None:
        raise ValueError(
            f"event {event_name!r} handler returned None. Return an object with emit, payload, "
            "and state."
        )
    if not isinstance(result, dict):
        raise ValueError(f"event {event_name!r} handlers must return an object")
    if not isinstance(result.get("emit"), bool):
        raise ValueError(f"event {event_name!r} result.emit must be a boolean")
    if "state" not in result:
        raise ValueError(f"event {event_name!r} result.state is required")
    if result["emit"] and "payload" not in result:
        raise ValueError(f"event {event_name!r} result.payload is required when emit=true")
