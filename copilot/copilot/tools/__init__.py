from copilot.tools.run_code import run_code
from copilot.tools.get_current_time import get_current_time
from copilot.tools.job_scheduler import (
    create_analysis_job,
    create_job,
    delete_job,
    list_jobs,
    run_job_now,
)

AVAILABLE_TOOLS = [
    run_code,
    get_current_time,
    create_job,
    create_analysis_job,
    list_jobs,
    run_job_now,
    delete_job,
]
