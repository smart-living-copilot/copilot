"""Agent tool registries.

This package re-exports local, runtime, and job-scheduling tools used by the
LangGraph nodes. `LOCAL_TOOLS` provides the ordered default local toolset
consumed by graph builders, while `REGISTRY_TOOLS` exposes discovered WoT tools.
"""

from copilot.agent.tools.run_code import run_code
from copilot.agent.tools.create_web_interface import create_web_interface
from copilot.agent.tools.get_current_time import get_current_time
from copilot.agent.tools.look_at_camera import look_at_camera
from copilot.agent.tools.wot_registry import REGISTRY_TOOLS as REGISTRY_TOOLS
from copilot.agent.tools.job_scheduler import (
    create_analysis_job,
    create_prompt_job,
    create_record_prompt_job,
    delete_job,
    list_jobs,
    run_job_now,
)
from copilot.agent.tools.virtual_things import define_virtual_thing, delete_virtual_thing

LOCAL_TOOLS = [
    run_code,
    create_web_interface,
    get_current_time,
    look_at_camera,
    create_prompt_job,
    create_analysis_job,
    list_jobs,
    create_record_prompt_job,
    define_virtual_thing,
    delete_virtual_thing,
    run_job_now,
    delete_job,
]

__all__ = [
    "LOCAL_TOOLS",
    "REGISTRY_TOOLS",
    "create_analysis_job",
    "create_prompt_job",
    "create_record_prompt_job",
    "create_web_interface",
    "delete_job",
    "delete_virtual_thing",
    "define_virtual_thing",
    "get_current_time",
    "list_jobs",
    "look_at_camera",
    "run_code",
    "run_job_now",
]
