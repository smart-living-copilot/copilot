from __future__ import annotations

import json
import math
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from copilot.catalog.validation import validate_document
from copilot.virtual_things.capabilities import infer_capabilities
from copilot.virtual_things.ids import make_virtual_thing_id

AffordanceType = Literal["property", "action", "event"]
BindingKind = Literal["record", "computed", "emitted"]
VirtualThingStatus = Literal["active", "disabled"]


class VirtualThingCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thing_id: str
    affordances: list[str] = Field(default_factory=list)
    ops: list[str] = Field(default_factory=list)


class VirtualThingTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["interval", "source_event", "explicit"]
    interval_seconds: int | None = Field(default=None, ge=1)
    thing_id: str | None = None
    event_name: str | None = None
    subscription_input: Any | None = None

    @model_validator(mode="after")
    def _validate_trigger(self) -> "VirtualThingTrigger":
        if self.kind == "interval" and self.interval_seconds is None:
            raise ValueError("interval triggers require interval_seconds")
        if self.kind == "source_event" and (not self.thing_id or not self.event_name):
            raise ValueError("source_event triggers require thing_id and event_name")
        return self


class VirtualThingBindingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affordance_type: AffordanceType
    affordance_name: str
    kind: BindingKind
    handler_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("handler_code", "handle"),
    )
    config: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[VirtualThingCapability] = Field(default_factory=list)
    trigger: VirtualThingTrigger | None = None
    state: Any | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    cache_ttl_seconds: int = Field(default=30, ge=0, le=3600)

    @field_validator("affordance_name")
    @classmethod
    def _name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("affordance_name is required")
        return value.strip()

    @field_validator("handler_code")
    @classmethod
    def _normalize_handler_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if _looks_like_javascript_handler(value):
            raise ValueError(
                "handler_code must be Python code that defines "
                "def handle(input, state, context), not JavaScript"
            )
        return value or None

    @model_validator(mode="before")
    @classmethod
    def _normalize_handler_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "affordance_name" not in normalized and "affordance" in normalized:
            normalized["affordance_name"] = normalized.pop("affordance")
        if "handler_code" not in normalized:
            for key in ("handle", "source", "code", "handler"):
                if key in normalized:
                    normalized["handler_code"] = normalized.pop(key)
                    break
        kind = normalized.get("kind")
        if kind == "event":
            normalized["kind"] = "emitted"
            normalized.setdefault("affordance_type", "event")
        elif kind == "action":
            normalized["kind"] = "computed"
            normalized.setdefault("affordance_type", "action")
        elif kind == "property":
            normalized["kind"] = "computed"
            normalized.setdefault("affordance_type", "property")
        if "trigger" not in normalized:
            if "interval_seconds" in normalized:
                normalized["trigger"] = {
                    "kind": "interval",
                    "interval_seconds": normalized.pop("interval_seconds"),
                }
            elif "evaluationInterval" in normalized:
                interval_ms = normalized.pop("evaluationInterval")
                if isinstance(interval_ms, (int, float)):
                    normalized["trigger"] = {
                        "kind": "interval",
                        "interval_seconds": max(1, math.ceil(interval_ms / 1000)),
                    }
        return normalized

    @model_validator(mode="after")
    def _validate_binding_shape(self) -> "VirtualThingBindingSpec":
        if self.kind in {"computed", "emitted"} and not self.handler_code:
            raise ValueError(f"{self.kind} bindings require handler_code")
        if self.kind == "emitted":
            if self.affordance_type != "event":
                raise ValueError("emitted bindings must bind events")
            if self.trigger is None:
                raise ValueError("emitted bindings require trigger")
        if self.kind == "computed" and self.affordance_type not in {"property", "action"}:
            raise ValueError("computed bindings only support properties and actions")
        return self

    @model_validator(mode="after")
    def _grant_inferred_capabilities(self) -> "VirtualThingBindingSpec":
        inferred = infer_capabilities(self.handler_code)
        if inferred:
            self.capabilities = _merge_capabilities(self.capabilities, inferred)
        return self


class DefineVirtualThingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(default=None, max_length=180)
    title: str = Field(min_length=1, max_length=120)
    description: str = ""
    td: dict[str, Any]
    bindings: list[VirtualThingBindingSpec]
    status: VirtualThingStatus = "active"
    owner_thread_id: str | None = Field(default=None, max_length=120)

    @model_validator(mode="before")
    @classmethod
    def _normalize_request_shorthand(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        bindings = normalized.get("bindings")
        td = normalized.get("td")
        events = td.get("events") if isinstance(td, dict) else {}
        if isinstance(bindings, list):
            normalized["bindings"] = [
                _normalize_binding_from_td(binding, events) for binding in bindings
            ]
        return normalized

    @model_validator(mode="after")
    def _normalize_and_validate(self) -> "DefineVirtualThingRequest":
        thing_id = self.id or make_virtual_thing_id(self.title)
        td = {**self.td, "id": thing_id, "title": self.title}
        if self.description:
            td["description"] = self.description
        self.id = thing_id
        self.td = validate_virtual_thing_td(td)
        _validate_binding_coverage(self.td, self.bindings)
        return self


class VirtualThingDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    owner_thread_id: str | None = None
    td: dict[str, Any]
    version: int
    status: VirtualThingStatus
    bindings: list[VirtualThingBindingSpec]


def _merge_capabilities(
    explicit: list[VirtualThingCapability],
    inferred: list[dict[str, Any]],
) -> list[VirtualThingCapability]:
    """Union explicitly declared grants with statically inferred ones by thing_id.

    Empty ``affordances`` means "every affordance", so it dominates a specific
    list when the two are merged for the same Thing.
    """
    grants: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def _accumulate(thing_id: str, ops: list[str], affordances: list[str]) -> None:
        grant = grants.get(thing_id)
        if grant is None:
            grant = {"ops": set(), "affordances": set(), "all_affordances": False}
            grants[thing_id] = grant
            order.append(thing_id)
        grant["ops"].update(ops)
        if affordances:
            grant["affordances"].update(affordances)
        else:
            grant["all_affordances"] = True

    for capability in explicit:
        _accumulate(capability.thing_id, capability.ops, capability.affordances)
    for capability in inferred:
        _accumulate(capability["thing_id"], capability["ops"], capability["affordances"])

    return [
        VirtualThingCapability(
            thing_id=thing_id,
            ops=sorted(grants[thing_id]["ops"]),
            affordances=(
                []
                if grants[thing_id]["all_affordances"]
                else sorted(grants[thing_id]["affordances"])
            ),
        )
        for thing_id in order
    ]


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True, default=str))


def validate_virtual_thing_td(td: Any) -> dict[str, Any]:
    if not isinstance(td, dict):
        raise ValueError("td must be an object")
    return json_safe(validate_document(_with_abstract_forms(td)))


def _with_abstract_forms(td: dict[str, Any]) -> dict[str, Any]:
    normalized = json_safe(td)
    normalized.setdefault("@context", "https://www.w3.org/2022/wot/td/v1.1")
    normalized.setdefault("securityDefinitions", {"nosec_sc": {"scheme": "nosec"}})
    normalized.setdefault("security", "nosec_sc")
    for section, op in (
        ("properties", "readproperty"),
        ("actions", "invokeaction"),
        ("events", "subscribeevent"),
    ):
        affordances = normalized.get(section)
        if not isinstance(affordances, dict):
            continue
        for name, definition in affordances.items():
            if not isinstance(definition, dict):
                continue
            if isinstance(definition.get("forms"), list) and definition["forms"]:
                continue
            definition["forms"] = [
                {
                    "href": f"urn:smart-living-copilot:virtual-things:{section}/{name}",
                    "op": [op],
                    "contentType": "application/json",
                }
            ]
    return normalized


def _validate_binding_coverage(
    td: dict[str, Any],
    bindings: list[VirtualThingBindingSpec],
) -> None:
    seen: set[tuple[str, str]] = set()
    for binding in bindings:
        key = (binding.affordance_type, binding.affordance_name)
        if key in seen:
            raise ValueError(
                f"duplicate binding for {binding.affordance_type} {binding.affordance_name}"
            )
        seen.add(key)
        section = {
            "property": "properties",
            "action": "actions",
            "event": "events",
        }[binding.affordance_type]
        affordances = td.get(section, {})
        if not isinstance(affordances, dict) or binding.affordance_name not in affordances:
            raise ValueError(
                f"binding references missing {binding.affordance_type} {binding.affordance_name!r}"
            )


def _looks_like_javascript_handler(value: str) -> bool:
    stripped = value.strip()
    return (
        stripped.startswith("function ")
        or stripped.startswith("return {")
        or "=>" in stripped
        or "??" in stripped
        or stripped.endswith("};")
    )


def _normalize_binding_from_td(binding: Any, events: Any) -> Any:
    if not isinstance(binding, dict):
        return binding
    normalized = dict(binding)
    affordance = normalized.get("affordance_name") or normalized.get("affordance")
    event_definition = (
        events.get(affordance) if isinstance(events, dict) and isinstance(affordance, str) else None
    )
    if (
        "trigger" not in normalized
        and isinstance(event_definition, dict)
        and isinstance(event_definition.get("evaluationInterval"), (int, float))
    ):
        normalized["evaluationInterval"] = event_definition["evaluationInterval"]
    return normalized
