from copilot.graph.tools.run_code import run_code
from copilot.graph.tools.get_current_time import get_current_time
from copilot.graph.tools.look_at_camera import look_at_camera
from copilot.graph.tools.registry import REGISTRY_TOOLS
from copilot.graph.tools.job_scheduler import (
    create_analysis_job,
    create_job,
    delete_job,
    list_jobs,
    run_job_now,
)

LOCAL_TOOLS = [
    run_code,
    get_current_time,
    look_at_camera,
    create_job,
    create_analysis_job,
    list_jobs,
    run_job_now,
    delete_job,
]

AVAILABLE_TOOLS = [*LOCAL_TOOLS, *REGISTRY_TOOLS]
