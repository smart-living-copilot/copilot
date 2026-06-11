from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from copilot.clients.code_executor import CodeExecutorClient
from copilot.virtual_things.schemas import json_safe

RESULT_PREFIX = "__VIRTUAL_THING_RESULT__"


class HandlerBinding(Protocol):
    id: str
    thing_id: str
    affordance_type: str
    affordance_name: str
    handler_code: str | None
    capabilities: Any
    config: Any
    timeout_seconds: int


class VirtualThingHandlerError(RuntimeError):
    """Raised when virtual handler code fails during execution."""


@dataclass(frozen=True)
class HandlerContext:
    thing_id: str
    affordance_type: str
    affordance_name: str
    capabilities: list[dict[str, Any]]
    config: dict[str, Any]


class VirtualThingHandlerRunner:
    """Runs computed and emitted virtual Thing handler code."""

    def __init__(self, code_executor: CodeExecutorClient) -> None:
        self._code_executor = code_executor

    async def run_handler(
        self,
        binding: HandlerBinding,
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
        code = handler_wrapper(
            handler_code=binding.handler_code,
            input_value=input_value,
            state={} if state is None else state,
            context=context,
        )
        try:
            response = await self._code_executor.execute(
                session_id=f"virtual-thing:{binding.id}",
                code=code,
                timeout_seconds=getattr(binding, "timeout_seconds", None),
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("computed handler timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise VirtualThingHandlerError(
                f"computed handler failed with status {exc.response.status_code}"
            ) from exc

        stdout = str(response.get("stdout", ""))
        for line in reversed(stdout.splitlines()):
            if line.startswith(RESULT_PREFIX):
                return json_safe(json.loads(line.removeprefix(RESULT_PREFIX)))
        raise VirtualThingHandlerError(stdout.strip() or "computed handler did not return a result")


def handler_wrapper(
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
    result_prefix_json = json.dumps(RESULT_PREFIX)
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
