from copilot.jobs.stores.base import (
    _json_safe,
    iso,
    job_run_thread_id_for_run,
    job_thread_id_for_job,
    JobNotWaitingForInput,
    JobRunNotCancellable,
    utc_now,
)
from copilot.jobs.stores.definitions import JobDefinitionStore
from copilot.jobs.stores.events import JobRunEventStore
from copilot.jobs.stores.runs import JobRunStore


class JobStore(JobDefinitionStore, JobRunStore, JobRunEventStore):
    """Aggregate store for job definitions, runs, and run events."""


__all__ = [
    "_json_safe",
    "iso",
    "job_run_thread_id_for_run",
    "job_thread_id_for_job",
    "JobDefinitionStore",
    "JobNotWaitingForInput",
    "JobRunEventStore",
    "JobRunNotCancellable",
    "JobRunStore",
    "JobStore",
    "utc_now",
]
