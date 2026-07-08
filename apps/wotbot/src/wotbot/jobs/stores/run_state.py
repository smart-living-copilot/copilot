from __future__ import annotations

from sqlalchemy.orm import Session

from wotbot.jobs.db import JobRecord, JobRunRecord
from wotbot.jobs.enums import JobActionKind, JobRunStatus
from wotbot.jobs.stores.base import job_run_thread_id_for_run


def _has_active_run(row: JobRecord) -> bool:
    return bool(row.active_run_id) or row.last_run_status in {
        JobRunStatus.RUNNING.value,
        JobRunStatus.WAITING_FOR_INPUT.value,
    }


def _job_thread_id_for_run_row(row: JobRecord, run_id: str) -> str:
    if row.action_kind == JobActionKind.PROMPT.value:
        return job_run_thread_id_for_run(row.id, run_id)
    return row.job_thread_id


def _active_or_last_run_id(row: JobRecord, *, missing_key: str) -> str:
    run_id = row.active_run_id or row.last_run_id
    if not run_id:
        raise KeyError(missing_key)
    return run_id


def _required_run_row(session: Session, run_id: str) -> JobRunRecord:
    run_row = session.get(JobRunRecord, run_id)
    if run_row is None:
        raise KeyError(run_id)
    return run_row
