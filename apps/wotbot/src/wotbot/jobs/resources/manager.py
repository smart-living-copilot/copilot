from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from wotbot.clients.wot_runtime import WotRuntimeClient
from wotbot.jobs.records import VirtualRecordStore
from wotbot.jobs.resources.constants import (
    RESOURCE_EVENT_SUBSCRIPTION,
    RESOURCE_SCHEDULE,
    RESOURCE_VIRTUAL_RECORD_THING,
)
from wotbot.jobs.resources.event_subscriptions import EventSubscriptionReconciler
from wotbot.jobs.resources.health import mark_resource_health
from wotbot.jobs.schedule import JobScheduleManager
from wotbot.jobs.schemas import (
    CreateJobRequest,
    EventTrigger,
    Job,
    JobDefinition,
    StructuredRecordOutput,
    TimeTrigger,
)
from wotbot.jobs.stores import JobStore, utc_now
from wotbot.jobs.subscriptions import subscription_id_from_response
from wotbot.virtual_things.enrichment import get_enrichment_scheduler

logger = logging.getLogger(__name__)


def _schedule_record_thing_enrichment(result: object) -> None:
    """Best-effort semantic enrichment of a freshly minted record-store Thing.

    Mirrors the virtual-Thing activation path: enrichment runs after the Thing is
    registered, is race-safe via the version compare-and-set in the scheduler, and is a
    no-op when there is no event loop or the registration result is incomplete.
    """
    if not isinstance(result, dict):
        return
    thing_id = result.get("thing_id")
    td = result.get("td")
    version = result.get("version")
    if isinstance(thing_id, str) and thing_id and isinstance(td, dict) and isinstance(version, int):
        get_enrichment_scheduler().schedule(thing_id, td, base_version=version)


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
            if not isinstance(job.output, StructuredRecordOutput):
                continue
            if not job.output.virtual_thing_id:
                logger.warning(
                    "Structured record job %s has no virtual Thing id during sync.",
                    job.id,
                )
                continue
            exists = await asyncio.to_thread(
                self._record_store.thing_exists,
                job.output.virtual_thing_id,
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
                await self._create_or_update_record_thing(job, _request=None)
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
        if isinstance(request.trigger, TimeTrigger):
            return PreparedJobResources(
                next_run_at=request.initial_next_run_at(now=utc_now()),
                subscription_id=None,
            )

        subscription_response = await self._event_subscriptions.subscribe_event_request(request)
        return PreparedJobResources(
            next_run_at=None,
            subscription_id=subscription_id_from_response(subscription_response),
        )

    async def prepare_definition(
        self,
        definition: JobDefinition,
        *,
        enabled: bool,
    ) -> PreparedJobResources:
        if isinstance(definition.trigger, TimeTrigger):
            return PreparedJobResources(
                next_run_at=definition.initial_next_run_at(now=utc_now(), enabled=enabled),
                subscription_id=None,
            )
        if not enabled:
            return PreparedJobResources(next_run_at=None, subscription_id=None)
        subscription_response = await self._runtime_client.subscribe_event(
            thing_id=definition.trigger.thing_id,
            event_name=definition.trigger.event_name,
            subscription_input=definition.trigger.subscription_input,
        )
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
        if isinstance(job.output, StructuredRecordOutput):
            await self._create_or_update_record_thing(job, _request=request)
        if isinstance(job.trigger, TimeTrigger):
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
        if isinstance(previous.trigger, TimeTrigger) and (
            not isinstance(updated.trigger, TimeTrigger) or not updated.enabled
        ):
            await self._schedule_manager.remove_job(previous.id)

        if previous.subscription_id and (
            not isinstance(updated.trigger, EventTrigger)
            or previous.subscription_id != updated.subscription_id
        ):
            await self._runtime_client.remove_subscription(
                subscription_id=previous.subscription_id,
            )
            if previous.subscription_id == updated.subscription_id:
                await self._repo.set_subscription_id(updated.id, None)
                updated = await self._repo.get_job(updated.id)

        previous_thing_id = (
            previous.output.virtual_thing_id
            if isinstance(previous.output, StructuredRecordOutput)
            else None
        )
        updated_thing_id = (
            updated.output.virtual_thing_id
            if isinstance(updated.output, StructuredRecordOutput)
            else None
        )
        if previous_thing_id and previous_thing_id != updated_thing_id:
            await asyncio.to_thread(self._record_store.delete_thing, previous_thing_id)

        if isinstance(updated.output, StructuredRecordOutput):
            await self._create_or_update_record_thing(updated, _request=None)

        if isinstance(updated.trigger, TimeTrigger):
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

        if isinstance(updated.trigger, EventTrigger):
            return await self._update_event_job_resources(previous, updated)

        return updated

    async def _update_event_job_resources(self, _previous: Job, updated: Job) -> Job:
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

        needs_subscription = updated.enabled and not updated.subscription_id
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
        if isinstance(job.trigger, TimeTrigger):
            await self._schedule_manager.remove_job(job.id)
        if job.subscription_id:
            await self._runtime_client.remove_subscription(
                subscription_id=job.subscription_id,
            )
        if isinstance(job.output, StructuredRecordOutput) and job.output.virtual_thing_id:
            await asyncio.to_thread(
                self._record_store.delete_thing,
                job.output.virtual_thing_id,
            )

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
        _request: CreateJobRequest | None,
    ) -> None:
        if not isinstance(job.output, StructuredRecordOutput):
            return
        virtual_thing = job.output.virtual_thing
        title = virtual_thing.title if virtual_thing is not None else None
        description = virtual_thing.description if virtual_thing is not None else None
        result = await asyncio.to_thread(
            self._record_store.create_or_update_thing,
            thing_id=job.output.virtual_thing_id or "",
            source_job_id=job.id,
            schema_version=job.output.schema_version,
            record_schema=job.output.schema or {},
            title=title or job.name,
            description=description or f"Structured records collected by the {job.name} job.",
        )
        _schedule_record_thing_enrichment(result)
        await mark_resource_health(
            self._repo,
            job.id,
            RESOURCE_VIRTUAL_RECORD_THING,
            "healthy",
        )
