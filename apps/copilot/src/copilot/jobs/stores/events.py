from __future__ import annotations

import asyncio

from sqlalchemy import select

from copilot.jobs.db import JobRunEventRecord
from copilot.jobs.schemas import JobRunEvent
from copilot.jobs.stores.base import _JobStoreBase, _to_job_run_event

class JobRunEventStore(_JobStoreBase):
    async def list_job_run_events(
        self,
        job_id: str,
        *,
        run_id: str | None = None,
    ) -> list[JobRunEvent]:
        return await asyncio.to_thread(self._list_job_run_events_sync, job_id, run_id)

    def _list_job_run_events_sync(
        self,
        job_id: str,
        run_id: str | None,
    ) -> list[JobRunEvent]:
        statement = select(JobRunEventRecord).where(JobRunEventRecord.job_id == job_id)
        if run_id is not None:
            statement = statement.where(JobRunEventRecord.run_id == run_id)
        statement = statement.order_by(
            JobRunEventRecord.created_at.asc(),
            JobRunEventRecord.id.asc(),
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job_run_event(row) for row in rows]
