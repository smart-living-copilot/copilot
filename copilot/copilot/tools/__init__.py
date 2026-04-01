from copilot.tools.run_code import run_code
from copilot.tools.get_current_time import get_current_time
from copilot.tools.job_scheduler import create_job, delete_job, list_jobs

AVAILABLE_TOOLS = [
    run_code,
    get_current_time,
    create_job,
    list_jobs,
    delete_job,
]
