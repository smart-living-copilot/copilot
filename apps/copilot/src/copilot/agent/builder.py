"""LangGraph assembly for the Smart Living Copilot agent."""

from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from copilot.agent.nodes import (
    CopilotState,
    make_analysis_node,
    make_control_node,
    make_jobs_node,
    make_respond_node,
    make_router_node,
    respond_should_continue,
)
from copilot.agent.tool_groups import group_local_tools, partition_registry_tools


def _tool_error_message(error: Exception) -> str:
    return f"Tool error: {error}"


def _after_tool_node(next_node: str):
    def route(state: CopilotState):
        messages = state.get("messages", [])
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                break
            if isinstance(message, ToolMessage) and message.name == "ask_job_user":
                return END
        return next_node

    return route


def build_graph(
    llm: ChatOpenAI,
    registry_tools: list[Any],
    local_tools: list[Any],
    max_tokens: int,
    checkpointer=None,
    parallel_tool_calls: bool = True,
    vision_enabled: bool = False,
):
    """Build and compile the copilot agent StateGraph."""
    registry_tool_groups = partition_registry_tools(registry_tools)
    local_tool_groups = group_local_tools(local_tools, vision_enabled=vision_enabled)

    vision_tools = (
        [local_tool_groups.look_at_camera]
        if local_tool_groups.look_at_camera
        else []
    )
    job_user_tools = (
        [local_tool_groups.ask_job_user]
        if local_tool_groups.ask_job_user
        else []
    )
    respond_tools = [local_tool_groups.get_current_time, *vision_tools, *job_user_tools]
    control_tools = (
        registry_tool_groups.discovery_and_inspect
        + registry_tool_groups.runtime
        + vision_tools
        + job_user_tools
    )
    analysis_tools = (
        registry_tool_groups.discovery_and_inspect
        + registry_tool_groups.runtime_read
        + [local_tool_groups.run_code]
        + vision_tools
        + job_user_tools
    )
    jobs_tools = (
        registry_tool_groups.discovery_and_inspect
        + registry_tool_groups.runtime_read
        + [local_tool_groups.run_code]
        + vision_tools
        + job_user_tools
        + local_tool_groups.job_tools
    )

    graph = StateGraph(CopilotState)

    graph.add_node("router", make_router_node(llm, max_tokens))
    graph.add_node(
        "respond",
        make_respond_node(
            llm,
            respond_tools,
            max_tokens,
            parallel_tool_calls=parallel_tool_calls,
        ),
    )
    graph.add_node(
        "jobs_llm",
        make_jobs_node(
            llm,
            jobs_tools,
            max_tokens,
            parallel_tool_calls=parallel_tool_calls,
        ),
    )
    graph.add_node(
        "jobs_tools",
        ToolNode(jobs_tools, handle_tool_errors=_tool_error_message),
    )
    graph.add_node(
        "respond_tools",
        ToolNode(respond_tools, handle_tool_errors=_tool_error_message),
    )
    graph.add_node(
        "control_llm",
        make_control_node(
            llm,
            control_tools,
            max_tokens,
            parallel_tool_calls=parallel_tool_calls,
        ),
    )
    graph.add_node(
        "control_tools",
        ToolNode(control_tools, handle_tool_errors=_tool_error_message),
    )
    graph.add_node(
        "analysis_llm",
        make_analysis_node(
            llm,
            analysis_tools,
            max_tokens,
            parallel_tool_calls=parallel_tool_calls,
        ),
    )
    graph.add_node(
        "analysis_tools",
        ToolNode(analysis_tools, handle_tool_errors=_tool_error_message),
    )

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        lambda state: state.get("intent", "chat"),
        {
            "chat": "respond",
            "control": "control_llm",
            "analysis": "analysis_llm",
            "jobs": "jobs_llm",
        },
    )

    graph.add_conditional_edges(
        "respond",
        respond_should_continue,
        {
            "tools": "respond_tools",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "respond_tools",
        _after_tool_node("respond"),
        {
            "respond": "respond",
            END: END,
        },
    )

    graph.add_conditional_edges(
        "control_llm",
        tools_condition,
        {
            "tools": "control_tools",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "control_tools",
        _after_tool_node("control_llm"),
        {
            "control_llm": "control_llm",
            END: END,
        },
    )

    graph.add_conditional_edges(
        "analysis_llm",
        tools_condition,
        {
            "tools": "analysis_tools",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "analysis_tools",
        _after_tool_node("analysis_llm"),
        {
            "analysis_llm": "analysis_llm",
            END: END,
        },
    )

    graph.add_conditional_edges(
        "jobs_llm",
        tools_condition,
        {
            "tools": "jobs_tools",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "jobs_tools",
        _after_tool_node("jobs_llm"),
        {
            "jobs_llm": "jobs_llm",
            END: END,
        },
    )

    return graph.compile(checkpointer=checkpointer)
