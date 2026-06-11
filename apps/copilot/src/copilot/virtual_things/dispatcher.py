from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from copilot.clients.code_executor import CodeExecutorClient
from copilot.core.settings import Settings
from copilot.jobs.records import VirtualRecordStore
from copilot.virtual_things.db import VirtualThingBinding
from copilot.virtual_things.schemas import json_safe
from copilot.virtual_things.store import VirtualThingStore

_RESULT_PREFIX = "__VIRTUAL_THING_RESULT__"
_CACHE: dict[str, tuple[float, Any]] = {}


class VirtualThingHandlerError(RuntimeError):
    """Raised when virtual handler code fails during execution."""


@dataclass(frozen=True)
class HandlerContext:
    thing_id: str
    affordance_type: str
    affordance_name: str
    capabilities: list[dict[str, Any]]
    config: dict[str, Any]


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
        cached = _cache_get(cache_key)
        if cached.found:
            return cached.value

        value = await self._run_handler(
            binding,
            input_value=None,
            state=binding.state,
        )
        if binding.cache_ttl_seconds > 0:
            _cache_set(cache_key, value, binding.cache_ttl_seconds)
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
        return await self._run_handler(binding, input_value=input_data, state=binding.state)

    async def evaluate_event(
        self,
        thing_id: str,
        event_name: str,
        trigger_input: Any,
        *,
        dry_run: bool = False,
    ) -> Any | None:
        binding = self._store.get_binding(
            thing_id=thing_id,
            affordance_type="event",
            affordance_name=event_name,
        )
        if binding.kind != "emitted":
            raise KeyError(event_name)
        result = await self._run_handler(
            binding,
            input_value=trigger_input,
            state=binding.state,
        )
        _validate_event_result(event_name, result)
        if not dry_run:
            self._store.update_binding_state(binding_id=binding.id, state=result.get("state"))
        emit = result["emit"]
        return result.get("payload") if emit else None

    async def _run_handler(
        self,
        binding: VirtualThingBinding,
        *,
        input_value: Any,
        state: Any,
    ) -> Any:
        if not binding.handler_code:
            raise ValueError("binding has no handler_code")
        context = HandlerContext(
            thing_id=binding.thing_id,
            affordance_type=binding.affordance_type,
            affordance_name=binding.affordance_name,
            capabilities=list(binding.capabilities or []),
            config=dict(binding.config or {}),
        )
        code = _handler_wrapper(
            handler_code=binding.handler_code,
            input_value=input_value,
            state={} if state is None else state,
            context=context,
        )
        try:
            response = await self._code_executor.execute(
                session_id=f"virtual-thing:{binding.id}",
                code=code,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("computed handler timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise VirtualThingHandlerError(
                f"computed handler failed with status {exc.response.status_code}"
            ) from exc

        stdout = str(response.get("stdout", ""))
        for line in reversed(stdout.splitlines()):
            if line.startswith(_RESULT_PREFIX):
                return json_safe(json.loads(line.removeprefix(_RESULT_PREFIX)))
        raise VirtualThingHandlerError(stdout.strip() or "computed handler did not return a result")


@dataclass(frozen=True)
class _CacheHit:
    found: bool
    value: Any = None


def _cache_get(key: str) -> _CacheHit:
    entry = _CACHE.get(key)
    if entry is None:
        return _CacheHit(found=False)
    expires_at, value = entry
    if expires_at <= time.monotonic():
        _CACHE.pop(key, None)
        return _CacheHit(found=False)
    return _CacheHit(found=True, value=value)


def _cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    _CACHE[key] = (time.monotonic() + ttl_seconds, json_safe(value))


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


def _handler_wrapper(
    *,
    handler_code: str,
    input_value: Any,
    state: Any,
    context: HandlerContext,
) -> str:
    payload = {
        "input": json_safe(input_value),
        "state": json_safe(state),
        "context": {
            "thing_id": context.thing_id,
            "affordance_type": context.affordance_type,
            "affordance_name": context.affordance_name,
            "capabilities": context.capabilities,
            "config": context.config,
        },
    }
    payload_json = json.dumps(payload, ensure_ascii=True)
    result_prefix_json = json.dumps(_RESULT_PREFIX)
    return f"""
import json as __vt_json
import sys as __vt_sys
import types as __vt_types

__vt_payload = __vt_json.loads({payload_json!r})
__vt_input = __vt_payload["input"]
__vt_state = __vt_payload["state"]
__vt_context = __vt_payload["context"]
__vt_caps = __vt_context.get("capabilities") or []
__vt_real_wot = wot

def __vt_check(op, thing_id, name):
    for cap in __vt_caps:
        if cap.get("thing_id") != thing_id:
            continue
        if op not in (cap.get("ops") or []):
            continue
        affordances = cap.get("affordances") or []
        if not affordances or name in affordances:
            return
    raise PermissionError(f"Virtual Thing handler is not allowed to {{op}} {{thing_id}}/{{name}}")

class __VirtualThingGuardedWot:
    def read_property(self, thing_id, property_name, uri_variables=None):
        __vt_check("readProperty", thing_id, property_name)
        return __vt_real_wot.read_property(thing_id, property_name, uri_variables)

    def write_property(self, thing_id, property_name, value, uri_variables=None):
        __vt_check("writeProperty", thing_id, property_name)
        return __vt_real_wot.write_property(thing_id, property_name, value, uri_variables)

    def invoke_action(self, thing_id, action_name, input=None, uri_variables=None):
        __vt_check("invokeAction", thing_id, action_name)
        return __vt_real_wot.invoke_action(thing_id, action_name, input, uri_variables)

wot = __VirtualThingGuardedWot()
__vt_wot_module = __vt_types.ModuleType("wot")
__vt_wot_module.read_property = wot.read_property
__vt_wot_module.write_property = wot.write_property
__vt_wot_module.invoke_action = wot.invoke_action
__vt_sys.modules["wot"] = __vt_wot_module

{handler_code}

if "handle" not in globals() or not callable(handle):
    raise RuntimeError("Virtual Thing handler_code must define handle(input, state, context)")

__vt_result = handle(__vt_input, __vt_state, __vt_context)
print({result_prefix_json} + __vt_json.dumps(__vt_result, ensure_ascii=True, default=str))
"""
