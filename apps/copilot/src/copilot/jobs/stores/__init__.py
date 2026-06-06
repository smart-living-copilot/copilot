"""Persistent job store composition.

The stores package composes definition, run, and run-event persistence into a
single high-level facade. Job persistence helpers in this module are used by
service code and job workers to read/write canonical run state.
"""

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
from copilot.jobs.stores.run_queries import JobRunQueryStore
from copilot.jobs.stores.runs import JobRunStore


class JobStore(JobDefinitionStore, JobRunStore, JobRunQueryStore, JobRunEventStore):
    """Aggregate store for job definitions, runs, run lookups, and run events."""


__all__ = [
    "_json_safe",
    "iso",
    "job_run_thread_id_for_run",
    "job_thread_id_for_job",
    "JobDefinitionStore",
    "JobNotWaitingForInput",
    "JobRunEventStore",
    "JobRunNotCancellable",
    "JobRunQueryStore",
    "JobRunStore",
    "JobStore",
    "utc_now",
]
