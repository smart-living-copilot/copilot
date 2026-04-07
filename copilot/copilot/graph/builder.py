"""LangGraph assembly for the Smart Living Copilot."""

from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from copilot.graph.nodes import (
    CopilotState,
    make_analysis_node,
    make_control_node,
    make_prune_node,
    make_respond_node,
    make_router_node,
    respond_should_continue,
)
from copilot.graph.tool_groups import group_local_tools, partition_mcp_tools


def build_graph(
    llm: ChatOpenAI,
    mcp_tools: list[Any],
    local_tools: list[Any],
    max_tokens: int,
    checkpointer=None,
    parallel_tool_calls: bool = True,
    max_checkpoint_tokens: int = 240_000,
):
    """Build and compile the copilot StateGraph."""
    mcp_tool_groups = partition_mcp_tools(mcp_tools)
    local_tool_groups = group_local_tools(local_tools)

    graph = StateGraph(CopilotState)

    graph.add_node("router", make_router_node(llm, max_tokens))

    respond_tools = [local_tool_groups.get_current_time]
    graph.add_node(
        "respond",
        make_respond_node(llm, respond_tools, max_tokens, parallel_tool_calls=parallel_tool_calls),
    )
    graph.add_node("respond_tools", ToolNode(respond_tools))

    control_tools = (
        mcp_tool_groups.discovery_and_inspect
        + mcp_tool_groups.runtime
        + local_tool_groups.job_tools
    )
    graph.add_node(
        "control_llm",
        make_control_node(llm, control_tools, max_tokens, parallel_tool_calls=parallel_tool_calls),
    )
    graph.add_node("control_tools", ToolNode(control_tools))

    analysis_tools = (
        mcp_tool_groups.discovery_and_inspect
        + mcp_tool_groups.runtime_read
        + [local_tool_groups.run_code]
        + local_tool_groups.job_tools
    )
    graph.add_node(
        "analysis_llm",
        make_analysis_node(
            llm, analysis_tools, max_tokens, parallel_tool_calls=parallel_tool_calls
        ),
    )
    graph.add_node("analysis_tools", ToolNode(analysis_tools))

    graph.add_node("prune_checkpoint", make_prune_node(max_checkpoint_tokens))

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        lambda state: state.get("intent", "chat"),
        {
            "chat": "respond",
            "control": "control_llm",
            "analysis": "analysis_llm",
        },
    )

    graph.add_conditional_edges(
        "respond",
        respond_should_continue,
        {
            "tools": "respond_tools",
            END: "prune_checkpoint",
        },
    )
    graph.add_edge("respond_tools", "respond")

    graph.add_conditional_edges(
        "control_llm",
        tools_condition,
        {
            "tools": "control_tools",
            END: "prune_checkpoint",
        },
    )
    graph.add_edge("control_tools", "control_llm")

    graph.add_conditional_edges(
        "analysis_llm",
        tools_condition,
        {
            "tools": "analysis_tools",
            END: "prune_checkpoint",
        },
    )
    graph.add_edge("analysis_tools", "analysis_llm")

    graph.add_edge("prune_checkpoint", END)

    return graph.compile(checkpointer=checkpointer)
