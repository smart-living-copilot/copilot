from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from copilot.jobs.db import JobRecord
from copilot.jobs.enums import JobTriggerKind
from copilot.jobs.schemas import CreateJobRequest, Job, JobDefinition
from copilot.jobs.stores.base import (
    _UNSET,
    _JobStoreBase,
    _json_safe,
    _source_thread_id_for_job,
    _to_job,
    _updated_resource_health,
    iso,
    job_thread_id_for_job,
    utc_now,
)
from copilot.threads.models import DEFAULT_THREAD_TITLE, Thread, ThreadKind


class JobDefinitionStore(_JobStoreBase):
    """Persists job definitions and their associated hidden job threads."""

    async def create_job(
        self,
        request: CreateJobRequest,
        *,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        return await asyncio.to_thread(self._create_job_sync, request, next_run_at, subscription_id)

    def _create_job_sync(
        self,
        request: CreateJobRequest,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        now = utc_now()
        job_id = str(uuid4())
        job_thread_id = job_thread_id_for_job(job_id)
        created_from_thread_id = _source_thread_id_for_job(request, job_id)
        with self._session_factory() as session:
            row = JobRecord(
                id=job_id,
                name=request.name,
                created_from_thread_id=created_from_thread_id,
                job_thread_id=job_thread_id,
                action_kind=request.action_kind.value,
                interaction_mode=request.interaction_mode.value,
                output_kind=request.output_kind.value,
                action=_json_safe(request.action.model_dump(mode="json", by_alias=True)),
                trigger=_json_safe(request.trigger.model_dump(mode="json", by_alias=True)),
                output=_json_safe(request.output.model_dump(mode="json", by_alias=True)),
                enabled=True,
                trigger_kind=request.trigger_kind.value,
                next_run_at=next_run_at,
                subscription_id=subscription_id,
                resource_health=None,
                created_at=now,
                updated_at=now,
                run_count=0,
            )
            thread = Thread(
                id=job_thread_id,
                title=f"Job: {request.name}"[:120] or DEFAULT_THREAD_TITLE,
                created_at=iso(now),
                updated_at=iso(now),
                kind=ThreadKind.JOB.value,
                visible=False,
                job_id=job_id,
            )
            session.add(row)
            session.add(thread)
            session.commit()
            return _to_job(row)

    async def get_job(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._get_job_sync, job_id)

    def _get_job_sync(self, job_id: str) -> Job:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise KeyError(job_id)
            return _to_job(row)

    async def get_job_by_thread_id(self, job_thread_id: str) -> Job:
        return await asyncio.to_thread(self._get_job_by_thread_id_sync, job_thread_id)

    def _get_job_by_thread_id_sync(self, job_thread_id: str) -> Job:
        statement = select(JobRecord).where(JobRecord.job_thread_id == job_thread_id)
        with self._session_factory() as session:
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_thread_id)
            return _to_job(row)

    async def list_jobs(self, created_from_thread_id: str | None = None) -> list[Job]:
        return await asyncio.to_thread(self._list_jobs_sync, created_from_thread_id)

    def _list_jobs_sync(self, created_from_thread_id: str | None = None) -> list[Job]:
        statement = select(JobRecord)
        if created_from_thread_id:
            statement = statement.where(JobRecord.created_from_thread_id == created_from_thread_id)
        statement = statement.order_by(JobRecord.created_at.desc())
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def delete_job(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._delete_job_sync, job_id)

    def _delete_job_sync(self, job_id: str) -> Job:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise KeyError(job_id)
            job = _to_job(row)
            thread = session.get(Thread, job.job_thread_id)
            if thread is not None:
                session.delete(thread)
            session.delete(row)
            session.commit()
            return job

    async def list_enabled_time_jobs(self) -> list[Job]:
        return await asyncio.to_thread(self._list_enabled_time_jobs_sync)

    def _list_enabled_time_jobs_sync(self) -> list[Job]:
        statement = (
            select(JobRecord)
            .where(
                JobRecord.trigger_kind == JobTriggerKind.TIME.value,
                JobRecord.enabled.is_(True),
            )
            .order_by(JobRecord.created_at.asc())
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def disable_job(self, job_id: str) -> None:
        await asyncio.to_thread(self._disable_job_sync, job_id)

    def _disable_job_sync(self, job_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                return
            row.enabled = False
            row.next_run_at = None
            row.updated_at = utc_now()
            session.commit()

    async def list_event_jobs_for_subscription(self, subscription_id: str) -> list[Job]:
        return await asyncio.to_thread(self._list_event_jobs_for_subscription_sync, subscription_id)

    def _list_event_jobs_for_subscription_sync(self, subscription_id: str) -> list[Job]:
        statement = select(JobRecord).where(
            JobRecord.trigger_kind == JobTriggerKind.EVENT.value,
            JobRecord.enabled.is_(True),
            JobRecord.subscription_id == subscription_id,
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def list_enabled_event_jobs(self) -> list[Job]:
        return await asyncio.to_thread(self._list_enabled_event_jobs_sync)

    def _list_enabled_event_jobs_sync(self) -> list[Job]:
        statement = select(JobRecord).where(
            JobRecord.trigger_kind == JobTriggerKind.EVENT.value,
            JobRecord.enabled.is_(True),
        )
        with self._session_factory() as session:
            rows = session.scalars(statement).all()
            return [_to_job(row) for row in rows]

    async def set_subscription_id(self, job_id: str, subscription_id: str | None) -> None:
        await asyncio.to_thread(self._set_subscription_id_sync, job_id, subscription_id)

    def _set_subscription_id_sync(self, job_id: str, subscription_id: str | None) -> None:
        with self._session_factory() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                return
            row.subscription_id = subscription_id
            row.updated_at = utc_now()
            session.commit()

    async def set_job_resource_health(
        self,
        job_id: str,
        *,
        resource: str,
        status: str,
        message: str | None = None,
        now: datetime | None = None,
    ) -> Job | None:
        return await asyncio.to_thread(
            self._set_job_resource_health_sync,
            job_id,
            resource,
            status,
            message,
            now or utc_now(),
        )

    def _set_job_resource_health_sync(
        self,
        job_id: str,
        resource: str,
        status: str,
        message: str | None,
        now: datetime,
    ) -> Job | None:
        with self._session_factory() as session:
            statement = select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            row = session.scalars(statement).one_or_none()
            if row is None:
                return None
            row.resource_health = _updated_resource_health(
                row.resource_health,
                resource=resource,
                status=status,
                message=message,
                now=now,
            )
            row.updated_at = now
            session.commit()
            return _to_job(row)

    async def update_job(
        self,
        job_id: str,
        *,
        name: object = _UNSET,
        enabled: object = _UNSET,
    ) -> Job:
        return await self.update_job_metadata(job_id, name=name, enabled=enabled)

    async def update_job_metadata(
        self,
        job_id: str,
        *,
        name: object = _UNSET,
        enabled: object = _UNSET,
    ) -> Job:
        return await asyncio.to_thread(
            self._update_job_metadata_sync,
            job_id,
            name,
            enabled,
        )

    def _update_job_metadata_sync(
        self,
        job_id: str,
        name: object,
        enabled: object,
    ) -> Job:
        now = utc_now()
        with self._session_factory() as session:
            statement = select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_id)

            if name is not _UNSET:
                row.name = name  # type: ignore[assignment]
            if enabled is not _UNSET:
                row.enabled = bool(enabled)

            row.next_run_at = self._compute_next_run_at(row, now)
            row.updated_at = now
            session.commit()
            return _to_job(row)

    async def replace_job_definition(
        self,
        job_id: str,
        definition: JobDefinition,
        *,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        return await asyncio.to_thread(
            self._replace_job_definition_sync,
            job_id,
            definition,
            next_run_at,
            subscription_id,
        )

    def _replace_job_definition_sync(
        self,
        job_id: str,
        definition: JobDefinition,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        now = utc_now()
        with self._session_factory() as session:
            statement = select(JobRecord).where(JobRecord.id == job_id).with_for_update()
            row = session.scalars(statement).one_or_none()
            if row is None:
                raise KeyError(job_id)

            row.interaction_mode = definition.interaction_mode.value
            row.action_kind = definition.action_kind.value
            row.trigger_kind = definition.trigger_kind.value
            row.output_kind = definition.output_kind.value
            row.action = _json_safe(definition.action.model_dump(mode="json", by_alias=True))
            row.trigger = _json_safe(definition.trigger.model_dump(mode="json", by_alias=True))
            row.output = _json_safe(definition.output.model_dump(mode="json", by_alias=True))
            row.next_run_at = next_run_at
            row.subscription_id = subscription_id
            row.updated_at = now
            session.commit()
            return _to_job(row)

    @staticmethod
    def _compute_next_run_at(row: JobRecord, now: datetime) -> datetime | None:
        if row.trigger_kind != JobTriggerKind.TIME.value or not row.enabled:
            return None
        try:
            return _to_job(row).next_run_at_after(now=now, enabled=row.enabled)
        except ValueError:
            return None
