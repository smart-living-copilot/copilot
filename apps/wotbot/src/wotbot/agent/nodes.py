"""Node helpers for the WoTBot agent graph."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any, Literal, NotRequired, Optional, cast

from copilotkit import CopilotKitState
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END
from langgraph.types import Command
from pydantic import BaseModel, Field

from wotbot.agent.device_interactions import (
    without_device_interaction_summary_messages,
)
from wotbot.agent.prompts import (
    ANALYSIS_PROMPT,
    CONTROL_PROMPT,
    JOBS_PROMPT,
    RESPOND_PROMPT,
    ROUTER_PROMPT,
    VIRTUAL_THINGS_PROMPT,
)
from wotbot.agent.tools.look_at_camera import is_look_at_camera_available
from wotbot.core.time import utc_now
from wotbot.jobs.enums import JobOutputKind

logger = logging.getLogger(__name__)

BACKGROUND_JOB_PROMPT = """\
You are executing one background prompt job run for WoTBot.

Follow the runtime instructions in the user message. This is not a foreground
conversation about creating or managing jobs; it is the job execution itself.

If the run needs human input, call ask_job_user with one concise question and
then stop. When the user has replied, use that answer to finish the same run.
Do not ask the same question again unless the answer is unusable or required
information is still missing.

For structured record jobs, call submit_job_record once the available data
matches the provided JSON Schema. Do not claim success before submit_job_record
returns ok=true.

When creating plots or charts with run_code, trigger artifact capture explicitly:
call plt.show() for Matplotlib figures or fig.show() for Plotly figures. Do not
only create a figure object and describe it.

Keep final responses concise and factual.
"""


class WotbotState(CopilotKitState):
    intent: str
    # Set by the route_to handoff tool to request continuation in another
    # branch; consumed and cleared by the dispatch node. Absent/None means the
    # turn ends normally. Only used when agent_handoff_enabled is set.
    next: NotRequired[Optional[str]]


class IntentClassification(BaseModel):
    intent: Literal["chat", "control", "analysis", "jobs", "virtual_things"] = Field(
        description="The classified intent"
    )


def _strip_wot_calls(message: BaseMessage) -> BaseMessage:
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


def _trim_conversation(messages: Sequence[BaseMessage], max_tokens: int) -> list[BaseMessage]:
    # Strip ``wot_calls`` BEFORE counting tokens: those device-interaction
    # payloads are removed from the prompt anyway, but a single run_code result
    # can carry megabytes of them. Trimming on the un-stripped messages let that
    # invisible data consume the whole budget and evict the real conversation.
    prepared = [
        _strip_wot_calls(message)
        for message in without_device_interaction_summary_messages(messages)
    ]
    trimmed = trim_messages(
        prepared,
        max_tokens=max_tokens,
        token_counter="approximate",
        strategy="last",
        include_system=True,
        allow_partial=True,
    )
    if trimmed and isinstance(trimmed[0], SystemMessage):
        trimmed.pop(0)
    return _sanitize_message_sequence(trimmed)


def _sanitize_message_sequence(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Ensure every AI tool_call has a matching ToolMessage and vice-versa."""
    sanitized: list[BaseMessage] = []
    index = 0

    while index < len(messages):
        message = messages[index]

        # AI message with tool calls: collect all following ToolMessages that match.
        if isinstance(message, AIMessage) and message.tool_calls:
            tool_messages: list[ToolMessage] = []
            next_index = index + 1
            while next_index < len(messages):
                next_message = messages[next_index]
                if not isinstance(next_message, ToolMessage):
                    break
                tool_messages.append(next_message)
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
            sanitized_message = message
            if len(matched_calls) != len(message.tool_calls):
                additional_kwargs = dict(message.additional_kwargs)
                if additional_kwargs.get("tool_calls"):
                    additional_kwargs["tool_calls"] = [
                        tool_call
                        for tool_call in additional_kwargs["tool_calls"]
                        if tool_call.get("id") in matched_ids
                    ]
                sanitized_message = message.model_copy(
                    update={
                        "tool_calls": matched_calls,
                        "additional_kwargs": additional_kwargs,
                    }
                )

            matched_tool_messages = [tm for tm in tool_messages if tm.tool_call_id in matched_ids]
            sanitized.append(sanitized_message)
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


def _make_router_messages(messages: Sequence[BaseMessage], max_tokens: int) -> list[BaseMessage]:
    trimmed = trim_messages(
        without_device_interaction_summary_messages(messages),
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


def _latest_run_code_source(messages: Sequence[BaseMessage]) -> str | None:
    """Return the source of the most recent run_code tool call, if any.

    The virtual_things branch has no run_code tool, and a large analysis result
    is usually trimmed out of its context window. Pinning the source lets the
    model reuse prior modelling logic instead of re-deriving it from scratch.
    """
    for message in reversed(messages):
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue
        for tool_call in message.tool_calls:
            if tool_call.get("name") != "run_code":
                continue
            args = tool_call.get("args") or {}
            source = args.get("code") if isinstance(args, dict) else None
            if isinstance(source, str) and source.strip():
                return source.strip()
    return None


def _prior_analysis_block(messages: Sequence[BaseMessage]) -> str:
    source = _latest_run_code_source(messages)
    if not source:
        return ""
    return f"\n\n## Prior Analysis Code\n```python\n{source}\n```"


def _current_time_block() -> str:
    now = utc_now()
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

    def prompt(state: WotbotState) -> list[BaseMessage]:
        trimmed = _trim_conversation(state["messages"], max_tokens)
        return [system_message, *trimmed]

    return prompt


def _active_tools_for_config(tools: list[Any], config: Optional[RunnableConfig]) -> list[Any]:
    if not tools:
        return []

    configurable = config.get("configurable", {}) if config else {}
    return [
        tool
        for tool in tools
        if (getattr(tool, "name", None) != "look_at_camera" or is_look_at_camera_available(config))
        and (
            getattr(tool, "name", None) != "submit_job_record"
            or configurable.get("job_output_kind") == JobOutputKind.STRUCTURED_RECORD.value
        )
    ]


def _thread_id_from_config(config: Optional[RunnableConfig]) -> str | None:
    configurable = config.get("configurable", {}) if config else {}
    thread_id = configurable.get("thread_id") or configurable.get("threadId")
    return thread_id if isinstance(thread_id, str) and thread_id else None


def _tool_names(tools: list[Any]) -> list[str]:
    return sorted(str(name) for tool in tools if (name := getattr(tool, "name", None)))


def _log_branch_entry(
    branch: str,
    *,
    config: Optional[RunnableConfig],
    active_tools: list[Any],
    parallel_tool_calls: bool,
) -> None:
    names = _tool_names(active_tools)
    logger.debug(
        "Agent branch entered branch=%s thread_id=%s tool_count=%d tools=%s parallel_tool_calls=%s",
        branch,
        _thread_id_from_config(config),
        len(names),
        names,
        parallel_tool_calls,
    )


def make_router_node(llm: ChatOpenAI, max_tokens: int):
    """Classify the current request into a single graph branch."""
    structured_llm = llm.with_structured_output(IntentClassification)
    system_message = SystemMessage(content=ROUTER_PROMPT)

    async def router(state: WotbotState, config: Optional[RunnableConfig] = None):
        tail = _make_router_messages(state["messages"], max_tokens)
        result = cast(
            IntentClassification,
            await structured_llm.ainvoke([system_message, *tail]),
        )
        logger.info(
            "Router classified intent thread_id=%s intent=%s",
            _thread_id_from_config(config),
            result.intent,
        )
        return {"intent": result.intent}

    return router


def _make_llm_node(
    llm: ChatOpenAI,
    *,
    tools: list[Any],
    system_text: str,
    max_tokens: int,
    parallel_tool_calls: bool = True,
    branch_name: str = "llm",
):
    prompt = _make_node_prompt(system_text, max_tokens)

    # NOTE: keep ``config`` typed as ``Optional[RunnableConfig]``. With
    # ``from __future__ import annotations`` the annotation is a string, and
    # LangGraph only injects the runtime config when it reads as
    # ``"RunnableConfig"`` or ``"Optional[RunnableConfig]"``. Writing it as
    # ``RunnableConfig | None`` silently disables injection, so ``config`` (and
    # the ``thread_id`` that look_at_camera needs) arrives as ``None``.
    async def node(state: WotbotState, config: Optional[RunnableConfig] = None):
        active_tools = _active_tools_for_config(tools, config)
        _log_branch_entry(
            branch_name,
            config=config,
            active_tools=active_tools,
            parallel_tool_calls=parallel_tool_calls,
        )
        runnable = (
            llm.bind_tools(active_tools, parallel_tool_calls=parallel_tool_calls)
            if active_tools
            else llm
        )
        response = await runnable.ainvoke(prompt(state))
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
        branch_name="respond",
    )


def make_control_node(
    llm: ChatOpenAI,
    tools: list[Any],
    max_tokens: int,
    *,
    parallel_tool_calls: bool = True,
    handoff_note: str = "",
):
    return _make_llm_node(
        llm,
        tools=tools,
        system_text=CONTROL_PROMPT + handoff_note,
        max_tokens=max_tokens,
        parallel_tool_calls=parallel_tool_calls,
        branch_name="control",
    )


def make_analysis_node(
    llm: ChatOpenAI,
    tools: list[Any],
    max_tokens: int,
    *,
    parallel_tool_calls: bool = True,
    handoff_note: str = "",
):
    # ``config`` typing must stay ``Optional[RunnableConfig]``; see _make_llm_node.
    async def node(state: WotbotState, config: Optional[RunnableConfig] = None):
        system_message = SystemMessage(
            content=ANALYSIS_PROMPT + handoff_note + _current_time_block()
        )
        trimmed = _trim_conversation(state["messages"], max_tokens)
        messages = [system_message, *trimmed]
        active_tools = _active_tools_for_config(tools, config)
        _log_branch_entry(
            "analysis",
            config=config,
            active_tools=active_tools,
            parallel_tool_calls=parallel_tool_calls,
        )
        runnable = (
            llm.bind_tools(active_tools, parallel_tool_calls=parallel_tool_calls)
            if active_tools
            else llm
        )
        response = await runnable.ainvoke(messages)
        return {"messages": [response]}

    return node


def make_jobs_node(
    llm: ChatOpenAI,
    tools: list[Any],
    max_tokens: int,
    *,
    parallel_tool_calls: bool = True,
    handoff_note: str = "",
):
    # ``config`` typing must stay ``Optional[RunnableConfig]``; see _make_llm_node.
    async def node(state: WotbotState, config: Optional[RunnableConfig] = None):
        system_message = SystemMessage(content=JOBS_PROMPT + handoff_note + _current_time_block())
        trimmed = _trim_conversation(state["messages"], max_tokens)
        messages = [system_message, *trimmed]
        active_tools = _active_tools_for_config(tools, config)
        _log_branch_entry(
            "jobs",
            config=config,
            active_tools=active_tools,
            parallel_tool_calls=parallel_tool_calls,
        )
        runnable = (
            llm.bind_tools(active_tools, parallel_tool_calls=parallel_tool_calls)
            if active_tools
            else llm
        )
        response = await runnable.ainvoke(messages)
        return {"messages": [response]}

    return node


def make_virtual_things_node(
    llm: ChatOpenAI,
    tools: list[Any],
    max_tokens: int,
    *,
    parallel_tool_calls: bool = True,
    handoff_note: str = "",
):
    # ``config`` typing must stay ``Optional[RunnableConfig]``; see _make_llm_node.
    async def node(state: WotbotState, config: Optional[RunnableConfig] = None):
        system_message = SystemMessage(
            content=VIRTUAL_THINGS_PROMPT
            + handoff_note
            + _prior_analysis_block(state["messages"])
            + _current_time_block()
        )
        trimmed = _trim_conversation(state["messages"], max_tokens)
        messages = [system_message, *trimmed]
        active_tools = _active_tools_for_config(tools, config)
        _log_branch_entry(
            "virtual_things",
            config=config,
            active_tools=active_tools,
            parallel_tool_calls=parallel_tool_calls,
        )
        runnable = (
            llm.bind_tools(active_tools, parallel_tool_calls=parallel_tool_calls)
            if active_tools
            else llm
        )
        response = await runnable.ainvoke(messages)
        return {"messages": [response]}

    return node


def make_background_job_node(
    llm: ChatOpenAI,
    tools: list[Any],
    max_tokens: int,
    *,
    parallel_tool_calls: bool = True,
):
    # ``config`` typing must stay ``Optional[RunnableConfig]``; see _make_llm_node.
    async def node(state: WotbotState, config: Optional[RunnableConfig] = None):
        system_message = SystemMessage(content=BACKGROUND_JOB_PROMPT + _current_time_block())
        trimmed = _trim_conversation(state["messages"], max_tokens)
        active_tools = _active_tools_for_config(tools, config)
        _log_branch_entry(
            "background_job",
            config=config,
            active_tools=active_tools,
            parallel_tool_calls=parallel_tool_calls,
        )
        runnable = (
            llm.bind_tools(active_tools, parallel_tool_calls=parallel_tool_calls)
            if active_tools
            else llm
        )
        response = await runnable.ainvoke([system_message, *trimmed])
        return {"messages": [response]}

    return node


def respond_should_continue(state: WotbotState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


def make_dispatch_node(targets: dict[str, str], *, finish_node: str):
    """Route a finished action branch into its requested successor branch.

    Reads ``state["next"]`` (set by the route_to handoff tool), clears it, and
    jumps to the mapped target node. When ``next`` is unset/unknown it falls
    through to ``finish_node`` — making the handoff path identical to the
    single-branch flow whenever no handoff was requested. Clearing and jumping
    happen atomically via ``Command`` so a stale field can never re-trigger.
    """

    def dispatch(state: WotbotState) -> Command:
        requested = state.get("next")
        goto = targets.get(requested, finish_node) if requested else finish_node
        if requested and goto == finish_node:
            logger.warning(
                "Agent handoff target unknown requested=%s resolved=%s",
                requested,
                finish_node,
            )
        elif requested:
            logger.info(
                "Agent handoff dispatch requested=%s resolved=%s",
                requested,
                goto,
            )
        else:
            logger.info("Agent handoff dispatch fallthrough resolved=%s", goto)
        return Command(goto=goto, update={"next": None})

    return dispatch
