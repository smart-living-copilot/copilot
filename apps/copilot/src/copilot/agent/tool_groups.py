"""Tool grouping helpers for the Smart Living Copilot agent graph.

The graph is handed two flat lists of LangChain tools (see ``agent.tools``):

* **registry tools** cover Thing catalog/search operations and the external
  ``wot_runtime`` service (live device reads, writes, action invocations,
  subscriptions).
* **local tools** are the copilot's own first-party tools: ``get_current_time``
  (in-process), ``run_code`` (code-executor), ``look_at_camera`` (vision model),
  the worker-only ``ask_job_user`` and ``submit_job_record`` tools, and the job API tools.

Each graph node only gets a subset of these (e.g. the chat ``respond`` node has
no device-write tools). This module is the single place that maps tool *names*
to those functional groups, so the routing policy lives in one spot instead of
being scattered across ``builder``.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Registry tools, grouped by what they do.
_DISCOVERY_NAMES = {"registry_health", "things_list", "things_search", "things_sparql"}
_INSPECT_NAMES = {
    "things_validate",
    "things_get",
    "wot_get_action",
    "wot_get_property",
    "wot_get_event",
}
_RUNTIME_READ_NAMES = {
    "wot_get_runtime_health",
    "wot_read_property",
    "wot_observe_property",
}
_RUNTIME_WRITE_NAMES = {
    "things_upsert",
    "things_delete",
    "wot_invoke_action",
    "wot_write_property",
    "wot_subscribe_event",
    "wot_remove_subscription",
}
_RUNTIME_NAMES = _RUNTIME_READ_NAMES | _RUNTIME_WRITE_NAMES

# Local tools that are referenced individually by the graph. Every other local
# tool is treated as a job API tool for the dedicated jobs branch, so adding a
# new job-management tool in ``agent.tools`` needs no change here.
_GET_CURRENT_TIME = "get_current_time"
_RUN_CODE = "run_code"
_CREATE_WEB_INTERFACE = "create_web_interface"
_LOOK_AT_CAMERA = "look_at_camera"
_ASK_JOB_USER = "ask_job_user"
_SUBMIT_JOB_RECORD = "submit_job_record"
_NAMED_LOCAL_NAMES = {
    _GET_CURRENT_TIME,
    _RUN_CODE,
    _CREATE_WEB_INTERFACE,
    _LOOK_AT_CAMERA,
    _ASK_JOB_USER,
    _SUBMIT_JOB_RECORD,
}


@dataclass(frozen=True)
class RegistryToolGroups:
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
    create_web_interface: Any | None
    look_at_camera: Any | None
    ask_job_user: Any | None
    submit_job_record: Any | None
    job_tools: list[Any]


def partition_registry_tools(registry_tools: list[Any]) -> RegistryToolGroups:
    """Split registry tools into functional groups by explicit name."""
    discovery: list[Any] = []
    inspect: list[Any] = []
    runtime: list[Any] = []
    runtime_read: list[Any] = []

    for tool in registry_tools:
        name = tool.name
        if name in _DISCOVERY_NAMES:
            discovery.append(tool)
        elif name in _INSPECT_NAMES:
            inspect.append(tool)
        elif name in _RUNTIME_NAMES:
            runtime.append(tool)
            if name in _RUNTIME_READ_NAMES:
                runtime_read.append(tool)
        else:
            logger.debug("Registry tool %r not assigned to any partition group", name)

    return RegistryToolGroups(
        discovery=discovery,
        inspect=inspect,
        runtime=runtime,
        runtime_read=runtime_read,
    )


def group_local_tools(
    local_tools: list[Any],
    *,
    vision_enabled: bool = False,
) -> LocalToolGroups:
    """Return the local tools required by the graph by their explicit names."""
    tools_by_name = {tool.name: tool for tool in local_tools}
    missing = [name for name in (_GET_CURRENT_TIME, _RUN_CODE) if name not in tools_by_name]
    if missing:
        raise ValueError(f"Missing required local tools: {', '.join(sorted(missing))}")

    return LocalToolGroups(
        get_current_time=tools_by_name[_GET_CURRENT_TIME],
        run_code=tools_by_name[_RUN_CODE],
        create_web_interface=tools_by_name.get(_CREATE_WEB_INTERFACE),
        look_at_camera=tools_by_name.get(_LOOK_AT_CAMERA) if vision_enabled else None,
        ask_job_user=tools_by_name.get(_ASK_JOB_USER),
        submit_job_record=tools_by_name.get(_SUBMIT_JOB_RECORD),
        job_tools=[tool for tool in local_tools if tool.name not in _NAMED_LOCAL_NAMES],
    )
