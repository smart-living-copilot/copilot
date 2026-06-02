from __future__ import annotations

import logging

from copilot.clients.wot_runtime import WotRuntimeClient
from copilot.jobs.resources.constants import RESOURCE_EVENT_SUBSCRIPTION
from copilot.jobs.resources.health import mark_resource_health
from copilot.jobs.schemas import CreateJobRequest, Job
from copilot.jobs.store import JobStore
from copilot.jobs.subscriptions import subscription_id_from_response

logger = logging.getLogger(__name__)


class EventSubscriptionReconciler:
    def __init__(
        self,
        *,
        repo: JobStore,
        runtime_client: WotRuntimeClient,
    ) -> None:
        self._repo = repo
        self._runtime_client = runtime_client

    async def sync(self) -> int:
        jobs = await self._repo.list_enabled_event_jobs()
        synced = 0
        for job in jobs:
            if job.subscription_id:
                try:
                    await self._runtime_client.remove_subscription(
                        subscription_id=job.subscription_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to remove stale runtime subscription for job %s: %s",
                        job.id,
                        exc,
                    )

            try:
                subscription_response = await self.subscribe_event_job(job)
                subscription_id = subscription_id_from_response(subscription_response)
                await self._repo.set_subscription_id(job.id, subscription_id)
                await mark_resource_health(
                    self._repo,
                    job.id,
                    RESOURCE_EVENT_SUBSCRIPTION,
                    "healthy",
                )
                synced += 1
            except Exception as exc:
                await mark_resource_health(
                    self._repo,
                    job.id,
                    RESOURCE_EVENT_SUBSCRIPTION,
                    "degraded",
                    str(exc),
                )
                logger.error("Failed to sync subscription for job %s: %s", job.id, exc)
        return synced

    async def subscribe_event_request(self, request: CreateJobRequest) -> dict:
        return await self._runtime_client.subscribe_event(
            thing_id=request.thing_id or "",
            event_name=request.event_name or "",
            subscription_input=request.subscription_input,
        )

    async def subscribe_event_job(self, job: Job) -> dict:
        return await self._runtime_client.subscribe_event(
            thing_id=job.thing_id or "",
            event_name=job.event_name or "",
            subscription_input=job.subscription_input,
        )
