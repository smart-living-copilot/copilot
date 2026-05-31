from copilot.agent.tools.run_code import run_code
from copilot.agent.tools.get_current_time import get_current_time
from copilot.agent.tools.look_at_camera import look_at_camera
from copilot.agent.tools.wot_registry import REGISTRY_TOOLS as REGISTRY_TOOLS
from copilot.agent.tools.job_scheduler import (
    create_analysis_job,
    create_prompt_job,
    delete_job,
    list_jobs,
    run_job_now,
)

LOCAL_TOOLS = [
    run_code,
    get_current_time,
    look_at_camera,
    create_prompt_job,
    create_analysis_job,
    list_jobs,
    run_job_now,
    delete_job,
]

__all__ = [
    "LOCAL_TOOLS",
    "REGISTRY_TOOLS",
    "create_analysis_job",
    "create_prompt_job",
    "delete_job",
    "get_current_time",
    "list_jobs",
    "look_at_camera",
    "run_code",
    "run_job_now",
]
