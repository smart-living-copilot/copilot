from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from copilot.jobs.db import JobRecord, JobRunRecord
from copilot.jobs.schemas import Job, JobRun
from copilot.jobs.stores.base import _JobStoreBase, _to_job, _to_job_run
from copilot.jobs.stores.replies import (
    _duplicate_reply_run,
    _normalize_client_reply_id,
    _reply_payload_has_client_reply_id,
)
from copilot.jobs.stores.run_state import _active_or_last_run_id, _required_run_row


class JobRunQueryStore(_JobStoreBase):
    """Read-only lookups over job runs.

    Split out from ``JobRunStore`` (the run state machine): these are stateless,
    lock-free single-statement reads with no shared mutation, so they live apart
    from the locked write transitions.
    """

    async def get_active_or_last_job_run(self, job_id: str) -> JobRun:
        return await asyncio.to_thread(self._get_active_or_last_job_run_sync, job_id)

    def _get_active_or_last_job_run_sync(self, job_id: str) -> JobRun:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise KeyError(job_id)
            run_id = _active_or_last_run_id(row, missing_key=job_id)
            return _to_job_run(_required_run_row(session, run_id))

    async def get_job_by_active_run_thread_id(self, job_thread_id: str) -> Job:
        return await asyncio.to_thread(self._get_job_by_active_run_thread_id_sync, job_thread_id)

    def _get_job_by_active_run_thread_id_sync(self, job_thread_id: str) -> Job:
        with self._session_factory() as session:
            statement = (
                select(JobRecord)
                .join(JobRunRecord, JobRunRecord.id == JobRecord.active_run_id)
                .where(JobRunRecord.job_thread_id == job_thread_id)
            )
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_thread_id)
            return _to_job(row)

    async def get_job_run(self, run_id: str) -> JobRun:
        return await asyncio.to_thread(self._get_job_run_sync, run_id)

    def _get_job_run_sync(self, run_id: str) -> JobRun:
        with self._session_factory() as session:
            row = session.get(JobRunRecord, run_id)
            if row is None:
                raise KeyError(run_id)
            return _to_job_run(row)

    async def get_job_run_by_client_reply_id(
        self,
        job_id: str,
        client_reply_id: str,
    ) -> JobRun | None:
        return await asyncio.to_thread(
            self._get_job_run_by_client_reply_id_sync,
            job_id,
            client_reply_id,
        )

    def _get_job_run_by_client_reply_id_sync(
        self,
        job_id: str,
        client_reply_id: str,
    ) -> JobRun | None:
        normalized = _normalize_client_reply_id(client_reply_id)
        if normalized is None:
            return None
        statement = (
            select(JobRunRecord)
            .where(JobRunRecord.job_id == job_id)
            .order_by(JobRunRecord.started_at.desc())
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            for row in rows:
                if _reply_payload_has_client_reply_id(row.trigger_payload, normalized):
                    return _duplicate_reply_run(row)
        return None

    async def get_latest_job_run(self, job_id: str) -> JobRun | None:
        return await asyncio.to_thread(self._get_latest_job_run_sync, job_id)

    def _get_latest_job_run_sync(self, job_id: str) -> JobRun | None:
        statement = (
            select(JobRunRecord)
            .where(JobRunRecord.job_id == job_id)
            .order_by(JobRunRecord.started_at.desc())
            .limit(1)
        )
        with self._session_factory() as session:
            row = session.scalars(statement).one_or_none()
            return _to_job_run(row) if row is not None else None

    async def get_job_by_thread_id_any(self, job_thread_id: str) -> Job:
        try:
            return await self.get_job_by_thread_id(job_thread_id)
        except KeyError:
            return await self.get_job_by_active_run_thread_id(job_thread_id)

    async def get_job_run_by_thread_id(self, job_thread_id: str) -> JobRun:
        return await asyncio.to_thread(self._get_job_run_by_thread_id_sync, job_thread_id)

    def _get_job_run_by_thread_id_sync(self, job_thread_id: str) -> JobRun:
        statement = select(JobRunRecord).where(JobRunRecord.job_thread_id == job_thread_id)
        with self._session_factory() as session:
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_thread_id)
            return _to_job_run(row)

    async def list_job_runs(
        self,
        job_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JobRun]:
        return await asyncio.to_thread(self._list_job_runs_sync, job_id, limit, offset)

    def _list_job_runs_sync(
        self,
        job_id: str,
        limit: int | None,
        offset: int,
    ) -> list[JobRun]:
        statement = (
            select(JobRunRecord)
            .where(JobRunRecord.job_id == job_id)
            .order_by(JobRunRecord.started_at.desc())
        )
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job_run(row) for row in rows]

    async def count_job_runs(self, job_id: str) -> int:
        return await asyncio.to_thread(self._count_job_runs_sync, job_id)

    def _count_job_runs_sync(self, job_id: str) -> int:
        statement = (
            select(func.count()).select_from(JobRunRecord).where(JobRunRecord.job_id == job_id)
        )
        with self._session_factory() as session:
            return int(session.scalar(statement) or 0)
