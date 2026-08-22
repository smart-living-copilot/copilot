"""Agent tool registries.

This package re-exports local, runtime, job-scheduling, and virtual Thing
authoring tools used by the LangGraph nodes. `LOCAL_TOOLS` provides the ordered
default local toolset consumed by graph builders, while `REGISTRY_TOOLS` exposes
discovered WoT tools.
"""

from wotbot.agent.tools.create_web_interface import create_web_interface
from wotbot.agent.tools.get_current_time import get_current_time
from wotbot.agent.tools.job_scheduler import (
    create_analysis_job,
    create_prompt_job,
    create_record_prompt_job,
    delete_job,
    list_jobs,
    run_job_now,
)
from wotbot.agent.tools.run_code import run_code
from wotbot.agent.tools.virtual_things import (
    activate_virtual_thing,
    add_virtual_action,
    add_virtual_event,
    add_virtual_property,
    create_virtual_thing,
    delete_virtual_thing,
    emit_virtual_thing_event,
)
from wotbot.agent.tools.wot_registry import REGISTRY_TOOLS as REGISTRY_TOOLS

LOCAL_TOOLS = [
    run_code,
    create_web_interface,
    get_current_time,
    create_prompt_job,
    create_analysis_job,
    list_jobs,
    create_record_prompt_job,
    create_virtual_thing,
    add_virtual_property,
    add_virtual_action,
    add_virtual_event,
    activate_virtual_thing,
    delete_virtual_thing,
    emit_virtual_thing_event,
    run_job_now,
    delete_job,
]

__all__ = [
    "LOCAL_TOOLS",
    "REGISTRY_TOOLS",
    "activate_virtual_thing",
    "add_virtual_action",
    "add_virtual_event",
    "add_virtual_property",
    "create_analysis_job",
    "create_prompt_job",
    "create_record_prompt_job",
    "create_virtual_thing",
    "create_web_interface",
    "delete_job",
    "delete_virtual_thing",
    "emit_virtual_thing_event",
    "get_current_time",
    "list_jobs",
    "run_code",
    "run_job_now",
]
