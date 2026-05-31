"""Automation jobs API backed by Taskiq workers."""

from copilot.jobs.routes import router
from copilot.jobs.service import JobService

__all__ = ["JobService", "router"]
