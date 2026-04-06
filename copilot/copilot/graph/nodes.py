"""Node helpers for the Smart Living Copilot LangGraph."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from copilotkit import CopilotKitState
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END
from pydantic import BaseModel, Field

from copilot.prompts import (
    ANALYSIS_PROMPT,
    CONTROL_PROMPT,
    RESPOND_PROMPT,
    ROUTER_PROMPT,
)

logger = logging.getLogger(__name__)


class CopilotState(CopilotKitState):
    intent: str = ""


class IntentClassification(BaseModel):
    intent: Literal["chat", "control", "analysis"] = Field(description="The classified intent")


def _strip_wot_calls(message: AnyMessage) -> AnyMessage:
    """Remove ``wot_calls`` from ToolMessage content before sending to the LLM.

    ``wot_calls`` are only needed by the UI to render device-interaction
    summaries.  They stay in the persisted graph state (so the frontend still
    receives them) but are stripped from the prompt to avoid blowing up the
    context with raw sensor data.
    """
    if not isinstance(message, ToolMessage):
        return message
    content = message.content
    if not isinstance(content, str):
        return message
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return message
    if not isinstance(parsed, dict) or "wot_calls" not in parsed:
        return message
    stripped = {k: v for k, v in parsed.items() if k != "wot_calls"}
    return message.model_copy(update={"content": json.dumps(stripped)})


def _trim_conversation(messages: list[AnyMessage], max_tokens: int) -> list[AnyMessage]:
    trimmed = trim_messages(
        messages,
        max_tokens=max_tokens,
        token_counter="approximate",
        strategy="last",
        include_system=True,
        allow_partial=True,
    )
    if trimmed and isinstance(trimmed[0], SystemMessage):
        trimmed.pop(0)
    sanitized = _sanitize_message_sequence(trimmed)
    return [_strip_wot_calls(m) for m in sanitized]


def _sanitize_message_sequence(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Ensure every AI tool_call has a matching ToolMessage and vice-versa."""
    sanitized: list[AnyMessage] = []
    index = 0

    while index < len(messages):
        message = messages[index]

        # AI message with tool calls: collect all following ToolMessages that match.
        if isinstance(message, AIMessage) and message.tool_calls:
            tool_messages: list[ToolMessage] = []
            next_index = index + 1
            while next_index < len(messages) and isinstance(messages[next_index], ToolMessage):
                tool_messages.append(messages[next_index])
                next_index += 1

            if not tool_messages:
                # No tool results at all — drop the AI tool-call message.
                index += 1
                continue

            # Keep only tool_calls that have a matching ToolMessage.
            matched_ids = {tm.tool_call_id for tm in tool_messages}
            matched_calls = [tc for tc in message.tool_calls if tc["id"] in matched_ids]

            if not matched_calls:
                index = next_index
                continue

            # Patch the AI message to only reference matched calls.
            if len(matched_calls) != len(message.tool_calls):
                message.tool_calls = matched_calls
                if message.additional_kwargs.get("tool_calls"):
                    message.additional_kwargs["tool_calls"] = [
                        tc
                        for tc in message.additional_kwargs["tool_calls"]
                        if tc.get("id") in matched_ids
                    ]

            matched_tool_messages = [tm for tm in tool_messages if tm.tool_call_id in matched_ids]
            sanitized.append(message)
            sanitized.extend(matched_tool_messages)
            index = next_index
            continue

        # Orphaned ToolMessage without preceding AI tool call — drop it.
        if isinstance(message, ToolMessage):
            index += 1
            continue

        sanitized.append(message)
        index += 1

    return sanitized


def _make_router_messages(messages: list[AnyMessage], max_tokens: int) -> list[AnyMessage]:
    trimmed = trim_messages(
        messages,
        max_tokens=max_tokens,
        token_counter="approximate",
        strategy="last",
        include_system=False,
        allow_partial=False,
    )
    sanitized = _sanitize_message_sequence(trimmed)
    conversational = [
        message
        for message in sanitized
        if not isinstance(message, ToolMessage)
        and not (isinstance(message, AIMessage) and message.tool_calls)
    ]
    tail = conversational[-3:]

    if not any(isinstance(message, HumanMessage) for message in tail):
        summary = "\n".join(
            f"{message.type}: {message.content}" for message in tail if message.content
        )
        tail = [HumanMessage(content=summary or "Classify the latest request.")]

    return tail


def _current_time_block() -> str:
    now = datetime.now(timezone.utc)
    ts_ms = int(now.timestamp() * 1000)
    ts_s = int(now.timestamp())
    return (
        f"\n\n## Current Time\n"
        f"Copy-paste these values directly into run_code. Do NOT reconstruct them with datetime.\n"
        f'- now_iso = "{now.isoformat()}"\n'
        f"- now_ts_s = {ts_s}\n"
        f"- now_ts_ms = {ts_ms}"
    )


def _make_node_prompt(system_text: str, max_tokens: int):
    system_message = SystemMessage(content=system_text)

    def prompt(state: CopilotState) -> list[AnyMessage]:
        trimmed = _trim_conversation(state["messages"], max_tokens)
        return [system_message, *trimmed]

    return prompt


def make_router_node(llm: ChatOpenAI, max_tokens: int):
    """Classify the current request into a single graph branch."""
    structured_llm = llm.with_structured_output(IntentClassification)
    system_message = SystemMessage(content=ROUTER_PROMPT)

    async def router(state: CopilotState):
        tail = _make_router_messages(state["messages"], max_tokens)
        result = await structured_llm.ainvoke([system_message, *tail])
        logger.info("Router classified intent as: %s", result.intent)
        return {"intent": result.intent}

    return router


def _make_llm_node(
    llm: ChatOpenAI,
    *,
    tools: list[Any],
    system_text: str,
    max_tokens: int,
    parallel_tool_calls: bool = True,
):
    prompt = _make_node_prompt(system_text, max_tokens)
    llm_with_tools = (
        llm.bind_tools(tools, parallel_tool_calls=parallel_tool_calls) if tools else llm
    )

    async def node(state: CopilotState):
        response = await llm_with_tools.ainvoke(prompt(state))
        return {"messages": [response]}

    return node


def make_respond_node(
    llm: ChatOpenAI,
    tools: list[Any],
    max_tokens: int,
    *,
    parallel_tool_calls: bool = True,
):
    return _make_llm_node(
        llm,
        tools=tools,
        system_text=RESPOND_PROMPT,
        max_tokens=max_tokens,
        parallel_tool_calls=parallel_tool_calls,
    )


def make_control_node(
    llm: ChatOpenAI,
    tools: list[Any],
    max_tokens: int,
    *,
    parallel_tool_calls: bool = True,
):
    return _make_llm_node(
        llm,
        tools=tools,
        system_text=CONTROL_PROMPT,
        max_tokens=max_tokens,
        parallel_tool_calls=parallel_tool_calls,
    )


def make_analysis_node(
    llm: ChatOpenAI,
    tools: list[Any],
    max_tokens: int,
    *,
    parallel_tool_calls: bool = True,
):
    llm_with_tools = llm.bind_tools(tools, parallel_tool_calls=parallel_tool_calls)

    async def node(state: CopilotState):
        system_message = SystemMessage(content=ANALYSIS_PROMPT + _current_time_block())
        trimmed = _trim_conversation(state["messages"], max_tokens)
        messages = [system_message, *trimmed]
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    return node


def make_prune_node(max_checkpoint_tokens: int):
    """Remove old messages from state so the persisted checkpoint stays bounded.

    Messages beyond ``max_checkpoint_tokens`` (oldest first) are pruned using
    ``RemoveMessage`` so the ``add_messages`` reducer drops them from the
    checkpoint.  The LLM prompt is already trimmed independently by
    ``_trim_conversation``, so this only affects the stored checkpoint size
    (and therefore cold-load time).
    """

    async def prune(state: CopilotState):
        messages: list[AnyMessage] = state["messages"]
        kept = trim_messages(
            messages,
            max_tokens=max_checkpoint_tokens,
            token_counter="approximate",
            strategy="last",
            include_system=True,
            allow_partial=False,
        )
        kept = _sanitize_message_sequence(kept)
        kept_ids = {m.id for m in kept}
        removals = [
            RemoveMessage(id=m.id) for m in messages if m.id not in kept_ids
        ]
        if removals:
            logger.info(
                "Pruning %d messages from checkpoint (%d kept)",
                len(removals),
                len(kept),
            )
        return {"messages": removals} if removals else {}

    return prune


def respond_should_continue(state: CopilotState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END
