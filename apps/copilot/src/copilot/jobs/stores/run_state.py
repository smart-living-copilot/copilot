from __future__ import annotations

from copilot.jobs.db import JobRecord
from copilot.jobs.enums import JobActionKind, JobRunStatus
from copilot.jobs.stores.base import job_run_thread_id_for_run


def _has_active_run(row: JobRecord) -> bool:
    return bool(row.active_run_id) or row.last_run_status in {
        JobRunStatus.RUNNING.value,
        JobRunStatus.WAITING_FOR_INPUT.value,
    }


def _job_thread_id_for_run_row(row: JobRecord, run_id: str) -> str:
    if row.action_kind == JobActionKind.PROMPT.value:
        return job_run_thread_id_for_run(row.id, run_id)
    return row.job_thread_id
