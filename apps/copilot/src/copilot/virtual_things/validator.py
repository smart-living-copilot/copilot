from __future__ import annotations

import ast
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from copilot.clients.code_executor import CodeExecutorClient
from copilot.core.settings import Settings
from copilot.virtual_things.capabilities import find_unscopable_wot_calls, infer_capabilities
from copilot.virtual_things.handler import VirtualThingHandlerRunner
from copilot.virtual_things.schemas import DefineVirtualThingRequest, VirtualThingBindingSpec

_ALLOWED_CAPABILITY_OPS = {"readProperty", "writeProperty", "invokeAction"}


@dataclass(frozen=True)
class ValidationIssue:
    affordance_type: str | None
    affordance_name: str | None
    phase: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "phase": self.phase,
            "message": self.message,
        }
        if self.affordance_type is not None:
            payload["affordance_type"] = self.affordance_type
        if self.affordance_name is not None:
            payload["affordance_name"] = self.affordance_name
        return payload


class VirtualThingValidator:
    """Validates standalone virtual Thing definitions before activation."""

    def __init__(
        self,
        *,
        code_executor: CodeExecutorClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._code_executor = code_executor or CodeExecutorClient(self._settings)

    def validate_static(self, request: DefineVirtualThingRequest) -> dict[str, Any]:
        issues: list[ValidationIssue] = []
        for binding in request.bindings:
            issues.extend(_static_binding_issues(binding))
        return _report(issues, smoke_tested=False)

    async def validate(
        self,
        request: DefineVirtualThingRequest,
        *,
        run_smoke: bool,
    ) -> dict[str, Any]:
        static_report = self.validate_static(request)
        issues = [_issue_from_payload(issue) for issue in static_report["issues"]]
        if issues or not run_smoke:
            return _report(issues, smoke_tested=False)

        handler_runner = VirtualThingHandlerRunner(self._code_executor)
        for binding in request.bindings:
            if binding.kind not in {"computed", "emitted"}:
                continue
            issues.extend(await self._smoke_binding(request, binding, handler_runner))
        return _report(issues, smoke_tested=True)

    async def _smoke_binding(
        self,
        request: DefineVirtualThingRequest,
        binding: VirtualThingBindingSpec,
        handler_runner: VirtualThingHandlerRunner,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for scenario in _smoke_scenarios(request, binding):
            try:
                result = await handler_runner.run_handler(
                    _runtime_binding(request, binding),
                    input_value=scenario.input_value,
                    state=scenario.state,
                    shared_state=request.shared_state,
                )
                _validate_contract(request, binding, result.value)
            except Exception as exc:
                issues.append(
                    ValidationIssue(
                        affordance_type=binding.affordance_type,
                        affordance_name=binding.affordance_name,
                        phase="smoke",
                        message=f"{scenario.label}: {exc}",
                    )
                )
                continue

            next_state = _result_state(result.value)
            if next_state is _MISSING:
                continue

            try:
                next_result = await handler_runner.run_handler(
                    _runtime_binding(request, binding),
                    input_value=scenario.input_value,
                    state=next_state,
                    shared_state=result.shared_state,
                )
                _validate_contract(request, binding, next_result.value)
            except Exception as exc:
                issues.append(
                    ValidationIssue(
                        affordance_type=binding.affordance_type,
                        affordance_name=binding.affordance_name,
                        phase="smoke",
                        message=f"{scenario.label} next state: {exc}",
                    )
                )

        return issues


@dataclass(frozen=True)
class _SmokeScenario:
    label: str
    input_value: Any
    state: Any


_MISSING = object()


def _smoke_scenarios(
    request: DefineVirtualThingRequest,
    binding: VirtualThingBindingSpec,
) -> list[_SmokeScenario]:
    input_value = _sample_input(request, binding)
    if binding.affordance_type != "event":
        return [
            _SmokeScenario(
                label="default input",
                input_value=input_value,
                state=_initial_state(binding),
            )
        ]

    scenarios = [
        _SmokeScenario(label="empty state", input_value=input_value, state={}),
    ]
    if binding.state not in (None, {}):
        scenarios.append(
            _SmokeScenario(label="configured state", input_value=input_value, state=binding.state)
        )

    if binding.trigger and binding.trigger.kind == "source_event":
        scenarios.append(
            _SmokeScenario(
                label="source event with empty payload",
                input_value={
                    "trigger": "source_event",
                    "source_thing_id": binding.trigger.thing_id,
                    "source_event_name": binding.trigger.event_name,
                    "payload": {},
                },
                state={},
            )
        )

    return scenarios


def _result_state(result: Any) -> Any:
    if not isinstance(result, dict) or "state" not in result:
        return _MISSING
    return result.get("state")


def _report(issues: list[ValidationIssue], *, smoke_tested: bool) -> dict[str, Any]:
    return {
        "ok": not issues,
        "smoke_tested": smoke_tested,
        "issues": [issue.as_dict() for issue in issues],
    }


def _issue_from_payload(payload: dict[str, Any]) -> ValidationIssue:
    return ValidationIssue(
        affordance_type=payload.get("affordance_type"),
        affordance_name=payload.get("affordance_name"),
        phase=str(payload.get("phase") or "static"),
        message=str(payload.get("message") or ""),
    )


def _static_binding_issues(binding: VirtualThingBindingSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if binding.kind in {"computed", "emitted"}:
        if not binding.handler_code:
            issues.append(_binding_issue(binding, "static", "handler_code is required"))
        else:
            issues.extend(_handler_code_issues(binding))
    if binding.kind == "emitted" and binding.trigger is None:
        issues.append(_binding_issue(binding, "static", "emitted event bindings require trigger"))
    for capability in binding.capabilities:
        if not capability.thing_id.strip():
            issues.append(_binding_issue(binding, "static", "capability thing_id is required"))
        unknown_ops = sorted(set(capability.ops) - _ALLOWED_CAPABILITY_OPS)
        if unknown_ops:
            issues.append(
                _binding_issue(
                    binding,
                    "static",
                    f"capability ops are not supported: {', '.join(unknown_ops)}",
                )
            )
    return issues


def _handler_code_issues(binding: VirtualThingBindingSpec) -> list[ValidationIssue]:
    assert binding.handler_code is not None
    try:
        module = ast.parse(binding.handler_code)
    except SyntaxError as exc:
        return [_binding_issue(binding, "static", f"handler_code is not valid Python: {exc.msg}")]
    handle_defs = [
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "handle"
    ]
    if not handle_defs:
        return [
            _binding_issue(
                binding,
                "static",
                "handler_code must define def handle(input, state, context)",
            )
        ]
    args = handle_defs[-1].args
    positional = [arg.arg for arg in args.posonlyargs + args.args]
    if positional != ["input", "state", "context"] or args.vararg or args.kwonlyargs or args.kwarg:
        return [
            _binding_issue(
                binding,
                "static",
                "handle signature must be exactly def handle(input, state, context)",
            )
        ]
    return _capability_coverage_issues(binding)


def _capability_coverage_issues(binding: VirtualThingBindingSpec) -> list[ValidationIssue]:
    """Flag wot calls the runtime guard will block for lack of a capability grant.

    A ``wot`` call with a non-literal thing_id cannot have its grant inferred, so
    unless the author declared a capability explicitly the guard rejects it at
    runtime. Catching it here turns a silent ``PermissionError`` into an authoring
    error the LLM can repair before activation.
    """
    unscopable = find_unscopable_wot_calls(binding.handler_code)
    if not unscopable:
        return []
    inferred = {grant["thing_id"] for grant in infer_capabilities(binding.handler_code)}
    explicit = {cap.thing_id for cap in (binding.capabilities or [])} - inferred
    if explicit:
        # The author declared grants beyond inference; trust them for the dynamic call.
        return []
    methods = ", ".join(f"wot.{method}" for method in unscopable)
    return [
        _binding_issue(
            binding,
            "static",
            f"{methods} is called with a non-literal thing_id, so the required "
            "capability grant cannot be inferred and the handler would be blocked "
            "at runtime. Pass literal thing_id and affordance strings (inline the "
            "values, e.g. iterate a literal list of (thing_id, name) tuples) or "
            "declare the capabilities explicitly.",
        )
    ]


def _binding_issue(
    binding: VirtualThingBindingSpec,
    phase: str,
    message: str,
) -> ValidationIssue:
    return ValidationIssue(
        affordance_type=binding.affordance_type,
        affordance_name=binding.affordance_name,
        phase=phase,
        message=message,
    )


def _initial_state(binding: VirtualThingBindingSpec) -> Any:
    return (
        {} if binding.state is None and binding.kind in {"computed", "emitted"} else binding.state
    )


def _runtime_binding(
    request: DefineVirtualThingRequest,
    binding: VirtualThingBindingSpec,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"validation:{request.id}:{binding.affordance_type}:{binding.affordance_name}",
        thing_id=request.id,
        affordance_type=binding.affordance_type,
        affordance_name=binding.affordance_name,
        kind=binding.kind,
        handler_code=binding.handler_code,
        capabilities=[
            capability.model_dump(mode="json") for capability in (binding.capabilities or [])
        ],
        config=dict(binding.config or {}),
        state=_initial_state(binding),
        timeout_seconds=binding.timeout_seconds,
        cache_ttl_seconds=binding.cache_ttl_seconds,
    )


def _sample_input(request: DefineVirtualThingRequest, binding: VirtualThingBindingSpec) -> Any:
    if binding.affordance_type == "action":
        schema = _affordance_schema(request, binding).get("input")
        return _sample_for_schema(schema) if isinstance(schema, dict) else None
    if binding.affordance_type == "event":
        if binding.trigger and binding.trigger.kind == "source_event":
            return {
                "trigger": "source_event",
                "source_thing_id": binding.trigger.thing_id,
                "source_event_name": binding.trigger.event_name,
                "payload": None,
            }
        if binding.trigger and binding.trigger.kind == "explicit":
            return {
                "trigger": "explicit",
                "input": None,
                "requested_at": "1970-01-01T00:00:00+00:00",
            }
        return {"trigger": "interval", "fired_at": "1970-01-01T00:00:00+00:00"}
    return None


def _sample_for_schema(schema: dict[str, Any]) -> Any:
    explicit_sample = _explicit_schema_sample(schema)
    if explicit_sample is not _NO_SAMPLE:
        return explicit_sample

    combiner_sample = _combiner_schema_sample(schema)
    if combiner_sample is not _NO_SAMPLE:
        return combiner_sample

    return _sample_for_schema_type(schema, _normalized_schema_type(schema))


_NO_SAMPLE = object()


def _explicit_schema_sample(schema: dict[str, Any]) -> Any:
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    return _NO_SAMPLE


def _combiner_schema_sample(schema: dict[str, Any]) -> Any:
    for combiner in ("oneOf", "anyOf", "allOf"):
        candidates = schema.get(combiner)
        if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
            return _sample_for_schema(candidates[0])
    return _NO_SAMPLE


def _normalized_schema_type(schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return next((item for item in schema_type if item != "null"), schema_type[0])
    return schema_type


def _sample_for_schema_type(schema: dict[str, Any], schema_type: Any) -> Any:
    sample_by_type = {
        "array": [],
        "integer": int(schema.get("minimum", 0)),
        "number": float(schema.get("minimum", 0)),
        "boolean": False,
        "null": None,
    }
    if schema_type == "object":
        return _sample_object_schema(schema)
    return sample_by_type.get(schema_type, "")


def _sample_object_schema(schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    return {
        name: _sample_for_schema(prop_schema)
        for name, prop_schema in properties.items()
        if isinstance(name, str) and isinstance(prop_schema, dict)
    }


def _validate_contract(
    request: DefineVirtualThingRequest,
    binding: VirtualThingBindingSpec,
    result: Any,
) -> None:
    if binding.affordance_type == "property":
        _validate_json_schema(
            _affordance_schema(request, binding),
            result,
            f"property {binding.affordance_name!r} result",
        )
        return
    if binding.affordance_type == "action":
        output_schema = _affordance_schema(request, binding).get("output")
        if isinstance(output_schema, dict):
            _validate_json_schema(
                output_schema,
                result,
                f"action {binding.affordance_name!r} output",
            )
        return
    _validate_event_contract(request, binding, result)


def _validate_event_contract(
    request: DefineVirtualThingRequest,
    binding: VirtualThingBindingSpec,
    result: Any,
) -> None:
    if result is None:
        raise ValueError(
            f"event {binding.affordance_name!r} handler returned None. Return an "
            "object with emit, payload, and state."
        )
    if not isinstance(result, dict):
        raise ValueError(f"event {binding.affordance_name!r} handler must return an object")
    if not isinstance(result.get("emit"), bool):
        raise ValueError(f"event {binding.affordance_name!r} result.emit must be a boolean")
    if "state" not in result:
        raise ValueError(f"event {binding.affordance_name!r} result.state is required")
    if result["emit"]:
        if "payload" not in result:
            raise ValueError(
                f"event {binding.affordance_name!r} result.payload is required when emit=true"
            )
        data_schema = _affordance_schema(request, binding).get("data")
        if isinstance(data_schema, dict):
            _validate_json_schema(
                data_schema,
                result.get("payload"),
                f"event {binding.affordance_name!r} payload",
            )


def _validate_json_schema(schema: dict[str, Any], value: Any, label: str) -> None:
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)
    except SchemaError as exc:
        raise ValueError(f"{label} schema is invalid: {exc.message}") from exc
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.path)
        location = f" at {path}" if path else ""
        raise ValueError(f"{label} failed schema validation{location}: {exc.message}") from exc


def _affordance_schema(
    request: DefineVirtualThingRequest,
    binding: VirtualThingBindingSpec,
) -> dict[str, Any]:
    section = {
        "property": "properties",
        "action": "actions",
        "event": "events",
    }[binding.affordance_type]
    affordances = request.td.get(section)
    if not isinstance(affordances, dict):
        return {}
    schema = affordances.get(binding.affordance_name)
    return schema if isinstance(schema, dict) else {}
