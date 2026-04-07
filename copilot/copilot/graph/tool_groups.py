"""Tool grouping helpers for the Smart Living Copilot graph."""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_DISCOVERY_NAMES = {"things_list", "things_search"}
_INSPECT_NAMES = {
    "things_get",
    "wot_get_action",
    "wot_get_property",
    "wot_get_event",
}
_RUNTIME_READ_NAMES = {
    "wot_read_property",
    "wot_observe_property",
}
_RUNTIME_WRITE_NAMES = {
    "wot_invoke_action",
    "wot_write_property",
    "wot_subscribe_event",
    "wot_remove_subscription",
}
_RUNTIME_NAMES = _RUNTIME_READ_NAMES | _RUNTIME_WRITE_NAMES


@dataclass(frozen=True)
class McpToolGroups:
    discovery: list[Any]
    inspect: list[Any]
    runtime: list[Any]
    runtime_read: list[Any]

    @property
    def discovery_and_inspect(self) -> list[Any]:
        return [*self.discovery, *self.inspect]


@dataclass(frozen=True)
class LocalToolGroups:
    get_current_time: Any
    run_code: Any
    job_tools: list[Any]


def partition_mcp_tools(mcp_tools: list[Any]) -> McpToolGroups:
    """Split MCP tools into functional groups by explicit name."""
    discovery: list[Any] = []
    inspect: list[Any] = []
    runtime: list[Any] = []

    for tool in mcp_tools:
        name = tool.name
        if name in _DISCOVERY_NAMES:
            discovery.append(tool)
        elif name in _INSPECT_NAMES:
            inspect.append(tool)
        elif name in _RUNTIME_NAMES:
            runtime.append(tool)
        else:
            logger.debug("MCP tool %r not assigned to any partition group", name)

    runtime_read = [tool for tool in runtime if tool.name in _RUNTIME_READ_NAMES]

    return McpToolGroups(
        discovery=discovery,
        inspect=inspect,
        runtime=runtime,
        runtime_read=runtime_read,
    )


def group_local_tools(local_tools: list[Any]) -> LocalToolGroups:
    """Return the local tools required by the graph by their explicit names."""
    tools_by_name = {tool.name: tool for tool in local_tools}
    missing = [
        tool_name
        for tool_name in ("get_current_time", "run_code")
        if tool_name not in tools_by_name
    ]
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"Missing required local tools: {missing_names}")

    return LocalToolGroups(
        get_current_time=tools_by_name["get_current_time"],
        run_code=tools_by_name["run_code"],
        job_tools=[
            tool
            for tool in local_tools
            if tool.name
            in {"create_job", "create_analysis_job", "list_jobs", "run_job_now", "delete_job"}
        ],
    )
