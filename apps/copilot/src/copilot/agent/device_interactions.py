"""Device-interaction summary helpers for graph UI markers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

DEVICE_INTERACTION_SUMMARY_TYPE = "smart_living_device_interactions"

WOT_DIRECT_TOOL_NAMES = {
    "wot_invoke_action",
    "wot_read_property",
    "wot_write_property",
    "wot_observe_property",
    "wot_subscribe_event",
}


def json_record(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    return value if isinstance(value, dict) else {}


def is_device_interaction_summary_message(message: BaseMessage) -> bool:
    if not isinstance(message, AIMessage):
        return False
    content = message.content
    if not isinstance(content, str):
        return False
    return json_record(content).get("type") == DEVICE_INTERACTION_SUMMARY_TYPE


def without_device_interaction_summary_messages(
    messages: Sequence[BaseMessage],
) -> list[BaseMessage]:
    return [message for message in messages if not is_device_interaction_summary_message(message)]


def make_device_interaction_summary_node():
    def node(state: dict[str, Any]):
        interactions = latest_turn_device_interactions(state.get("messages", []))
        if not interactions:
            return {}

        summary = {
            "type": DEVICE_INTERACTION_SUMMARY_TYPE,
            "interactions": interactions,
        }
        return {
            "messages": [
                AIMessage(content=json.dumps(summary, ensure_ascii=True)),
            ]
        }

    return node


def latest_turn_device_interactions(messages_value: Any) -> list[dict[str, Any]]:
    if not isinstance(messages_value, list):
        return []

    messages = list(messages_value)
    latest_user_index = _latest_user_message_index(messages)
    if latest_user_index < 0:
        return []

    turn_messages = _messages_after_latest_user(messages, latest_user_index)
    tool_calls_by_id = _tool_calls_by_id(turn_messages)

    interactions: list[dict[str, Any]] = []
    for message in turn_messages:
        interactions.extend(_tool_message_device_interactions(message, tool_calls_by_id))

    return interactions


def _latest_user_message_index(messages: Sequence[Any]) -> int:
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return index
    return -1


def _messages_after_latest_user(
    messages: Sequence[BaseMessage],
    latest_user_index: int,
) -> list[BaseMessage]:
    return [
        message
        for message in messages[latest_user_index + 1 :]
        if not is_device_interaction_summary_message(message)
    ]


def _tool_calls_by_id(messages: Sequence[BaseMessage]) -> dict[str, dict[str, Any]]:
    tool_calls: dict[str, dict[str, Any]] = {}
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for tool_call in message.tool_calls:
            tool_call_id = tool_call.get("id")
            if isinstance(tool_call_id, str):
                tool_calls[tool_call_id] = tool_call
    return tool_calls


def _tool_message_device_interactions(
    message: BaseMessage,
    tool_calls_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(message, ToolMessage):
        return []

    tool_call = tool_calls_by_id.get(message.tool_call_id)
    if not tool_call:
        return []

    tool_name = tool_call.get("name")
    if tool_name == "run_code":
        return _run_code_wot_interactions(message.content)

    if not isinstance(tool_name, str):
        return []

    interaction = _direct_wot_interaction(
        tool_name=tool_name,
        args=tool_call.get("args"),
        result=message.content,
    )
    return [interaction] if interaction else []


def _optional_record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) and value else None


def _is_error_result(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower().startswith("error")

    if isinstance(value, dict):
        error = value.get("error")
        return isinstance(error, str) and bool(error.strip())

    return False


def _normalize_wot_interaction(value: Any) -> dict[str, Any] | None:
    candidate = json_record(value)
    interaction_type = candidate.get("type")
    thing_id = candidate.get("thing_id") or candidate.get("thingId")
    if not isinstance(interaction_type, str) or not isinstance(thing_id, str):
        return None

    affordance_name = candidate.get("name") or candidate.get("affordanceName") or ""
    interaction: dict[str, Any] = {
        "affordanceName": affordance_name if isinstance(affordance_name, str) else "",
        "ok": candidate.get("ok") is not False,
        "thingId": thing_id,
        "type": interaction_type,
    }
    if "input" in candidate:
        interaction["input"] = candidate["input"]
    if "value" in candidate:
        interaction["value"] = candidate["value"]

    uri_variables = _optional_record(
        candidate.get("uri_variables") or candidate.get("uriVariables")
    )
    if uri_variables:
        interaction["uriVariables"] = uri_variables

    return interaction


def _run_code_wot_interactions(content: Any) -> list[dict[str, Any]]:
    parsed = json_record(content)
    raw_calls = parsed.get("wot_calls", [])
    if not isinstance(raw_calls, list):
        return []

    interactions: list[dict[str, Any]] = []
    for raw_call in raw_calls:
        interaction = _normalize_wot_interaction(raw_call)
        if interaction:
            interactions.append(interaction)
    return interactions


def _direct_wot_interaction(
    *,
    tool_name: str,
    args: Any,
    result: Any,
) -> dict[str, Any] | None:
    if tool_name not in WOT_DIRECT_TOOL_NAMES:
        return None

    parsed_args = json_record(args)
    thing_id = parsed_args.get("thing_id")
    if not isinstance(thing_id, str) or not thing_id:
        return None

    affordance_name = (
        parsed_args.get("action_name")
        or parsed_args.get("property_name")
        or parsed_args.get("event_name")
        or ""
    )
    interaction: dict[str, Any] = {
        "affordanceName": affordance_name if isinstance(affordance_name, str) else "",
        "ok": not _is_error_result(json_record(result) or result),
        "thingId": thing_id,
        "type": tool_name.replace("wot_", ""),
    }

    if "input" in parsed_args:
        interaction["input"] = parsed_args["input"]
    if "value" in parsed_args:
        interaction["value"] = parsed_args["value"]

    uri_variables = _optional_record(parsed_args.get("uri_variables"))
    if uri_variables:
        interaction["uriVariables"] = uri_variables

    return interaction
