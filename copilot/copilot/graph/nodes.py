"""Node helpers for the Smart Living Copilot LangGraph."""

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from copilotkit import CopilotKitState
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from copilot.prompts import (
    ANALYSIS_PROMPT,
    CONTROL_PROMPT,
    RESPOND_PROMPT,
    ROUTER_PROMPT,
)

logger = logging.getLogger(__name__)

_MAX_TOOL_CONTENT_CHARS = 4000


class CopilotState(CopilotKitState):
    intent: str = ""


class IntentClassification(BaseModel):
    intent: Literal["chat", "control", "analysis"] = Field(description="The classified intent")


class TruncatingToolNode(ToolNode):
    """ToolNode that truncates oversized tool responses."""

    async def ainvoke(self, input, config=None, **kwargs):
        result = await super().ainvoke(input, config=config, **kwargs)
        if isinstance(result, dict) and "messages" in result:
            result["messages"] = [self._truncate(message) for message in result["messages"]]
        return result

    @staticmethod
    def _truncate(message):
        if not isinstance(message, ToolMessage):
            return message
        content = message.content
        if isinstance(content, str) and len(content) > _MAX_TOOL_CONTENT_CHARS:
            message.content = (
                content[:_MAX_TOOL_CONTENT_CHARS]
                + "\n\n… truncated. Use wot_get_action or wot_get_property"
                " to inspect specific affordances."
            )
        return message


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
    return _sanitize_message_sequence(trimmed)


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


def respond_should_continue(state: CopilotState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END
