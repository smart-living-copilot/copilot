"""LangGraph assembly for the Smart Living Copilot agent."""

from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from copilot.agent.device_interactions import make_device_interaction_summary_node
from copilot.agent.nodes import (
    CopilotState,
    make_analysis_node,
    make_background_job_node,
    make_control_node,
    make_dispatch_node,
    make_jobs_node,
    make_respond_node,
    make_router_node,
    make_virtual_things_node,
    respond_should_continue,
)
from copilot.agent.prompts import HANDOFF_PROMPT
from copilot.agent.tool_groups import group_local_tools, partition_registry_tools
from copilot.agent.tools.route_to import make_route_to_tool


def _tool_error_message(error: Exception) -> str:
    return f"Tool error: {error}"


def _after_tool_node(next_node: str):
    def route(_state: CopilotState):
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
    handoff_enabled: bool = False,
):
    """Build and compile the copilot agent StateGraph."""
    registry_tool_groups = partition_registry_tools(registry_tools)
    local_tool_groups = group_local_tools(local_tools, vision_enabled=vision_enabled)

    vision_tools = [local_tool_groups.look_at_camera] if local_tool_groups.look_at_camera else []
    web_interface_tools = (
        [local_tool_groups.create_web_interface] if local_tool_groups.create_web_interface else []
    )
    job_runtime_tools = [
        tool
        for tool in (
            local_tool_groups.ask_job_user,
            local_tool_groups.submit_job_record,
        )
        if tool
    ]
    respond_tools = [local_tool_groups.get_current_time, *vision_tools, *job_runtime_tools]
    control_tools = (
        registry_tool_groups.discovery_and_inspect
        + registry_tool_groups.runtime
        + web_interface_tools
        + vision_tools
        + job_runtime_tools
    )
    analysis_tools = (
        registry_tool_groups.discovery_and_inspect
        + registry_tool_groups.runtime_read
        + [local_tool_groups.run_code]
        + web_interface_tools
        + vision_tools
        + job_runtime_tools
    )
    jobs_tools = (
        registry_tool_groups.discovery_and_inspect
        + registry_tool_groups.runtime_read
        + [local_tool_groups.run_code]
        + vision_tools
        + job_runtime_tools
        + local_tool_groups.job_tools
    )
    virtual_things_tools = (
        registry_tool_groups.discovery_and_inspect
        + registry_tool_groups.virtual_authoring_runtime
        + local_tool_groups.virtual_thing_tools
    )

    # When handoff is enabled, give the action branches the route_to tool so they
    # can continue the turn in another branch, and a system-prompt note telling
    # them how. Off by default: the tool lists, prompts, and edges below stay
    # exactly as the single-branch graph.
    handoff_note = ""
    if handoff_enabled:
        route_to = make_route_to_tool()
        control_tools = control_tools + [route_to]
        analysis_tools = analysis_tools + [route_to]
        jobs_tools = jobs_tools + [route_to]
        virtual_things_tools = virtual_things_tools + [route_to]
        handoff_note = HANDOFF_PROMPT

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
            handoff_note=handoff_note,
        ),
    )
    graph.add_node(
        "jobs_tools",
        ToolNode(jobs_tools, handle_tool_errors=_tool_error_message),
    )
    graph.add_node(
        "virtual_things_llm",
        make_virtual_things_node(
            llm,
            virtual_things_tools,
            max_tokens,
            parallel_tool_calls=parallel_tool_calls,
            handoff_note=handoff_note,
        ),
    )
    graph.add_node(
        "virtual_things_tools",
        ToolNode(virtual_things_tools, handle_tool_errors=_tool_error_message),
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
            handoff_note=handoff_note,
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
            handoff_note=handoff_note,
        ),
    )
    graph.add_node(
        "analysis_tools",
        ToolNode(analysis_tools, handle_tool_errors=_tool_error_message),
    )
    graph.add_node("device_summary", make_device_interaction_summary_node())

    # Action branches end at "dispatch" (which either continues into another
    # branch or falls through to device_summary) when handoff is enabled,
    # otherwise straight at "device_summary" as in the single-branch graph.
    action_branch_end = "device_summary"
    if handoff_enabled:
        action_branch_end = "dispatch"
        graph.add_node(
            "dispatch",
            make_dispatch_node(
                {
                    "control": "control_llm",
                    "analysis": "analysis_llm",
                    "jobs": "jobs_llm",
                    "virtual_things": "virtual_things_llm",
                },
                finish_node="device_summary",
            ),
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
            "virtual_things": "virtual_things_llm",
        },
    )

    graph.add_conditional_edges(
        "respond",
        respond_should_continue,
        {
            "tools": "respond_tools",
            END: "device_summary",
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
            END: action_branch_end,
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
            END: action_branch_end,
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
            END: action_branch_end,
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
    graph.add_conditional_edges(
        "virtual_things_llm",
        tools_condition,
        {
            "tools": "virtual_things_tools",
            END: action_branch_end,
        },
    )
    graph.add_conditional_edges(
        "virtual_things_tools",
        _after_tool_node("virtual_things_llm"),
        {
            "virtual_things_llm": "virtual_things_llm",
            END: END,
        },
    )
    graph.add_edge("device_summary", END)

    return graph.compile(checkpointer=checkpointer)


def build_background_job_graph(
    llm: ChatOpenAI,
    registry_tools: list[Any],
    local_tools: list[Any],
    max_tokens: int,
    checkpointer=None,
    parallel_tool_calls: bool = True,
    vision_enabled: bool = False,
):
    """Build and compile the compact graph used by background prompt jobs."""
    registry_tool_groups = partition_registry_tools(registry_tools)
    local_tool_groups = group_local_tools(local_tools, vision_enabled=vision_enabled)
    vision_tools = [local_tool_groups.look_at_camera] if local_tool_groups.look_at_camera else []
    job_tools = (
        registry_tool_groups.discovery_and_inspect
        + registry_tool_groups.runtime
        + [local_tool_groups.run_code, local_tool_groups.get_current_time]
        + vision_tools
        + [
            tool
            for tool in (
                local_tool_groups.ask_job_user,
                local_tool_groups.submit_job_record,
            )
            if tool
        ]
    )

    graph = StateGraph(CopilotState)
    graph.add_node(
        "job_llm",
        make_background_job_node(
            llm,
            job_tools,
            max_tokens,
            parallel_tool_calls=parallel_tool_calls,
        ),
    )
    graph.add_node(
        "job_tools",
        ToolNode(job_tools, handle_tool_errors=_tool_error_message),
    )
    graph.add_edge(START, "job_llm")
    graph.add_conditional_edges(
        "job_llm",
        tools_condition,
        {
            "tools": "job_tools",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "job_tools",
        _after_tool_node("job_llm"),
        {
            "job_llm": "job_llm",
            END: END,
        },
    )
    return graph.compile(checkpointer=checkpointer)
