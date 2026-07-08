"""Persistent job store composition.

The stores package composes definition, run, and run-event persistence into a
single high-level facade. Job persistence helpers in this module are used by
service code and job workers to read/write canonical run state.
"""

from wotbot.jobs.stores.base import (
    JobNotWaitingForInput,
    JobRunNotCancellable,
    _json_safe,
    iso,
    job_run_thread_id_for_run,
    job_thread_id_for_job,
    utc_now,
)
from wotbot.jobs.stores.definitions import JobDefinitionStore
from wotbot.jobs.stores.events import JobRunEventStore
from wotbot.jobs.stores.run_queries import JobRunQueryStore
from wotbot.jobs.stores.runs import JobRunStore


class JobStore(JobDefinitionStore, JobRunStore, JobRunQueryStore, JobRunEventStore):
    """Aggregate store for job definitions, runs, run lookups, and run events."""


__all__ = [
    "JobDefinitionStore",
    "JobNotWaitingForInput",
    "JobRunEventStore",
    "JobRunNotCancellable",
    "JobRunQueryStore",
    "JobRunStore",
    "JobStore",
    "_json_safe",
    "iso",
    "job_run_thread_id_for_run",
    "job_thread_id_for_job",
    "utc_now",
]
