from __future__ import annotations

import logging

from wotbot.clients.wot_runtime import WotRuntimeClient
from wotbot.jobs.resources.constants import RESOURCE_EVENT_SUBSCRIPTION
from wotbot.jobs.resources.health import mark_resource_health
from wotbot.jobs.schemas import CreateJobRequest, EventTrigger, Job
from wotbot.jobs.stores import JobStore
from wotbot.jobs.subscriptions import subscription_id_from_response

logger = logging.getLogger(__name__)


class EventSubscriptionReconciler:
    """Keeps runtime event subscriptions aligned with enabled event jobs."""

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
        if not isinstance(request.trigger, EventTrigger):
            raise ValueError("event subscription requires event trigger")
        return await self._runtime_client.subscribe_event(
            thing_id=request.trigger.thing_id,
            event_name=request.trigger.event_name,
            subscription_input=request.trigger.subscription_input,
        )

    async def subscribe_event_job(self, job: Job) -> dict:
        if not isinstance(job.trigger, EventTrigger):
            raise ValueError("event subscription requires event trigger")
        return await self._runtime_client.subscribe_event(
            thing_id=job.trigger.thing_id,
            event_name=job.trigger.event_name,
            subscription_input=job.trigger.subscription_input,
        )
