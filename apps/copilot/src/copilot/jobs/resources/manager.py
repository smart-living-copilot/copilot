from __future__ import annotations

import asyncio
import logging

from dataclasses import dataclass
from datetime import datetime

from copilot.clients.wot_runtime import WotRuntimeClient
from copilot.jobs.enums import JobOutputKind, JobTriggerKind
from copilot.jobs.records import VirtualRecordStore
from copilot.jobs.resources.constants import (
    RESOURCE_EVENT_SUBSCRIPTION,
    RESOURCE_SCHEDULE,
    RESOURCE_VIRTUAL_RECORD_THING,
)
from copilot.jobs.resources.event_subscriptions import EventSubscriptionReconciler
from copilot.jobs.resources.health import mark_resource_health
from copilot.jobs.schedule import JobScheduleManager
from copilot.jobs.schemas import CreateJobRequest, Job
from copilot.jobs.stores import JobStore, utc_now
from copilot.jobs.subscriptions import subscription_id_from_response
from copilot.jobs.time_schedule import initial_next_run_at_for_request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedJobResources:
    """External resource handles prepared before the job row is committed."""

    next_run_at: datetime | None
    subscription_id: str | None


class JobResourceManager:
    """Coordinates resources derived from the job row.

    The database row is still the source of truth, but schedules, runtime
    subscriptions and virtual record Things have to be created and cleaned up in
    lockstep with that row. Keeping that saga here makes the service layer a
    command facade instead of a place where resource rollback details accumulate.
    """

    def __init__(
        self,
        *,
        repo: JobStore,
        runtime_client: WotRuntimeClient,
        schedule_manager: JobScheduleManager,
        record_store: VirtualRecordStore,
    ) -> None:
        self._repo = repo
        self._runtime_client = runtime_client
        self._schedule_manager = schedule_manager
        self._record_store = record_store
        self._event_subscriptions = EventSubscriptionReconciler(
            repo=repo,
            runtime_client=runtime_client,
        )

    async def sync(self) -> None:
        await self._schedule_manager.sync()
        await self.sync_record_things()

    async def sync_record_things(self) -> int:
        jobs = await self._repo.list_jobs()
        repaired = 0
        for job in jobs:
            if job.output_kind != JobOutputKind.STRUCTURED_RECORD:
                continue
            if not job.virtual_thing_id:
                logger.warning(
                    "Structured record job %s has no virtual Thing id during sync.",
                    job.id,
                )
                continue
            exists = await asyncio.to_thread(
                self._record_store.thing_exists,
                job.virtual_thing_id,
            )
            if exists:
                await mark_resource_health(
                    self._repo,
                    job.id,
                    RESOURCE_VIRTUAL_RECORD_THING,
                    "healthy",
                )
                continue
            try:
                await self._create_or_update_record_thing(job, request=None)
                repaired += 1
            except Exception as exc:
                await mark_resource_health(
                    self._repo,
                    job.id,
                    RESOURCE_VIRTUAL_RECORD_THING,
                    "degraded",
                    str(exc),
                )
                logger.error(
                    "Failed to repair structured record Thing for job %s: %s",
                    job.id,
                    exc,
                )

        if repaired:
            logger.info("Repaired %d structured record Thing(s).", repaired)
        return repaired

    async def sync_event_subscriptions(self) -> int:
        return await self._event_subscriptions.sync()

    async def create_job(self, request: CreateJobRequest) -> Job:
        prepared = await self.prepare_create(request)
        try:
            job = await self._repo.create_job(
                request,
                next_run_at=prepared.next_run_at,
                subscription_id=prepared.subscription_id,
            )
        except Exception:
            await self.cleanup_prepared_create(prepared)
            raise

        try:
            await self.ensure_job_resources(job, request=request)
        except Exception:
            await self.cleanup_created_job_after_failure(job)
            raise
        return job

    async def prepare_create(self, request: CreateJobRequest) -> PreparedJobResources:
        if request.trigger_kind == JobTriggerKind.TIME:
            return PreparedJobResources(
                next_run_at=_next_run_at_for_time_request(request),
                subscription_id=None,
            )

        subscription_response = await self._event_subscriptions.subscribe_event_request(request)
        return PreparedJobResources(
            next_run_at=None,
            subscription_id=subscription_id_from_response(subscription_response),
        )

    async def ensure_job_resources(
        self,
        job: Job,
        *,
        request: CreateJobRequest | None = None,
    ) -> None:
        if job.output_kind == JobOutputKind.STRUCTURED_RECORD:
            await self._create_or_update_record_thing(job, request=request)
        if job.trigger_kind == JobTriggerKind.TIME:
            try:
                await self._schedule_manager.add_job(job)
            except Exception as exc:
                await mark_resource_health(
                    self._repo,
                    job.id,
                    RESOURCE_SCHEDULE,
                    "degraded",
                    str(exc),
                )
                raise
            await mark_resource_health(self._repo, job.id, RESOURCE_SCHEDULE, "healthy")

    async def update_job_resources(self, previous: Job, updated: Job) -> Job:
        if updated.trigger_kind == JobTriggerKind.TIME:
            try:
                await self._schedule_manager.remove_job(updated.id)
                if updated.enabled:
                    await self._schedule_manager.add_job(updated)
            except Exception as exc:
                await mark_resource_health(
                    self._repo,
                    updated.id,
                    RESOURCE_SCHEDULE,
                    "degraded",
                    str(exc),
                )
                raise
            await mark_resource_health(
                self._repo,
                updated.id,
                RESOURCE_SCHEDULE,
                "healthy",
            )
            return updated

        if updated.trigger_kind == JobTriggerKind.EVENT:
            return await self._update_event_job_resources(previous, updated)

        return updated

    async def _update_event_job_resources(self, previous: Job, updated: Job) -> Job:
        if not updated.enabled:
            if updated.subscription_id:
                try:
                    await self._runtime_client.remove_subscription(
                        subscription_id=updated.subscription_id,
                    )
                    await self._repo.set_subscription_id(updated.id, None)
                except Exception as exc:
                    await mark_resource_health(
                        self._repo,
                        updated.id,
                        RESOURCE_EVENT_SUBSCRIPTION,
                        "degraded",
                        str(exc),
                    )
                    raise
                await mark_resource_health(
                    self._repo,
                    updated.id,
                    RESOURCE_EVENT_SUBSCRIPTION,
                    "healthy",
                )
                return await self._repo.get_job(updated.id)
            await mark_resource_health(
                self._repo,
                updated.id,
                RESOURCE_EVENT_SUBSCRIPTION,
                "healthy",
            )
            return updated

        needs_subscription = not updated.subscription_id or not previous.enabled
        if not needs_subscription:
            return updated

        try:
            if updated.subscription_id:
                await self._runtime_client.remove_subscription(
                    subscription_id=updated.subscription_id,
                )
            subscription_response = await self._event_subscriptions.subscribe_event_job(updated)
            subscription_id = subscription_id_from_response(subscription_response)
            await self._repo.set_subscription_id(updated.id, subscription_id)
        except Exception as exc:
            await mark_resource_health(
                self._repo,
                updated.id,
                RESOURCE_EVENT_SUBSCRIPTION,
                "degraded",
                str(exc),
            )
            raise
        await mark_resource_health(
            self._repo,
            updated.id,
            RESOURCE_EVENT_SUBSCRIPTION,
            "healthy",
        )
        return await self._repo.get_job(updated.id)

    async def delete_job(self, job_id: str) -> Job:
        job = await self._repo.get_job(job_id)
        await self.delete_job_resources(job)
        return await self._repo.delete_job(job_id)

    async def delete_job_resources(self, job: Job) -> None:
        if job.trigger_kind == JobTriggerKind.TIME:
            await self._schedule_manager.remove_job(job.id)
        if job.subscription_id:
            await self._runtime_client.remove_subscription(
                subscription_id=job.subscription_id,
            )
        if job.virtual_thing_id:
            await asyncio.to_thread(self._record_store.delete_thing, job.virtual_thing_id)

    async def cleanup_prepared_create(self, prepared: PreparedJobResources) -> None:
        if not prepared.subscription_id:
            return
        try:
            await self._runtime_client.remove_subscription(
                subscription_id=prepared.subscription_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to remove runtime subscription %s after job creation failed: %s",
                prepared.subscription_id,
                exc,
            )

    async def cleanup_created_job_after_failure(self, job: Job) -> None:
        try:
            await self.delete_job_resources(job)
        except Exception as exc:
            logger.warning("Failed to clean external resources for job %s: %s", job.id, exc)
        try:
            await self._repo.delete_job(job.id)
        except Exception as exc:
            logger.warning("Failed to delete job %s after creation failed: %s", job.id, exc)

    async def _create_or_update_record_thing(
        self,
        job: Job,
        *,
        request: CreateJobRequest | None,
    ) -> None:
        title = request.virtual_thing_title if request is not None else None
        description = request.virtual_thing_description if request is not None else None
        await asyncio.to_thread(
            self._record_store.create_or_update_thing,
            thing_id=job.virtual_thing_id or "",
            source_job_id=job.id,
            schema_version=job.record_schema_version or 1,
            record_schema=job.record_schema or {},
            title=title or job.name,
            description=description or f"Structured records collected by the {job.name} job.",
        )
        await mark_resource_health(
            self._repo,
            job.id,
            RESOURCE_VIRTUAL_RECORD_THING,
            "healthy",
        )


def _next_run_at_for_time_request(request: CreateJobRequest) -> datetime | None:
    return initial_next_run_at_for_request(
        request,
        now=utc_now(),
    )
