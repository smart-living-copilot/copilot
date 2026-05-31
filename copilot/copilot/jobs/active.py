"""Process-wide handle to the running JobService.

Kept in its own lightweight module (no taskiq/broker imports) so the agent tools can
reach the in-process JobService without creating an import cycle through
``jobs.service`` -> ``jobs.taskiq_app`` -> ``jobs.executor`` -> ``agent.tools``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from copilot.jobs.service import JobService

_active_job_service: JobService | None = None


def set_active_job_service(service: JobService | None) -> None:
    global _active_job_service
    _active_job_service = service


def get_active_job_service() -> JobService | None:
    return _active_job_service
