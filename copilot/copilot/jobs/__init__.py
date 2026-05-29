"""In-process automation engine: time and event based jobs.

Merged from the former standalone ``job-runner`` service. ``JobService`` owns
the scheduler and event-stream loops; ``router`` exposes the job CRUD API.
"""

from copilot.jobs.routes import router
from copilot.jobs.service import JobService

__all__ = ["JobService", "router"]
