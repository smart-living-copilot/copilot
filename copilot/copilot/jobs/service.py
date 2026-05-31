from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from taskiq.exceptions import TaskiqResultTimeoutError

from copilot.core.settings import Settings
from copilot.jobs.models import CreateJobRequest, Job
from copilot.jobs.results import JobRunEventStream
from copilot.jobs.schedule import JobScheduleManager, build_schedule_source
from copilot.jobs.store import JobStore, utc_now
from copilot.jobs.subscriptions import subscription_id_from_response
from copilot.jobs.taskiq_app import broker, run_job_task
from copilot.wot_runtime.client import WotRuntimeClient

logger = logging.getLogger(__name__)


class JobService:
    def __init__(
        self,
        settings: Settings,
        *,
        repo: JobStore | None = None,
        runtime_client: WotRuntimeClient | None = None,
        run_event_stream: JobRunEventStream | None = None,
        schedule_manager: JobScheduleManager | None = None,
    ) -> None:
        self._settings = settings
        self._repo = repo or JobStore()
        self._runtime_client = runtime_client or WotRuntimeClient(settings)
        self._run_event_stream = run_event_stream or JobRunEventStream(settings)
        self._schedule_manager = schedule_manager or JobScheduleManager(
            build_schedule_source(settings),
            repo=self._repo,
        )

    async def start(self) -> None:
        await broker.startup()
        await self._schedule_manager.sync()

    async def stop(self) -> None:
        await broker.shutdown()

    async def create_job(self, request: CreateJobRequest) -> Job:
        self._validate_request(request)

        next_run_at = None
        subscription_id = None
        if request.trigger_type == "time":
            if request.run_at is not None:
                next_run_at = request.run_at
            elif request.interval_seconds is not None:
                next_run_at = utc_now() + timedelta(seconds=request.interval_seconds)
        else:
            subscription_response = await self._runtime_client.subscribe_event(
                thing_id=request.thing_id or "",
                event_name=request.event_name or "",
                subscription_input=request.subscription_input,
            )
            subscription_id = subscription_id_from_response(subscription_response)

        try:
            job = await self._repo.create_job(
                request,
                next_run_at=next_run_at,
                subscription_id=subscription_id,
            )
        except Exception:
            if subscription_id:
                await self._remove_subscription_after_create_failure(subscription_id)
            raise

        if job.trigger_type == "time":
            try:
                await self._schedule_manager.add_job(job)
            except Exception:
                await self._cleanup_created_job_after_create_failure(job)
                raise
        return job

    async def get_job(self, job_id: str) -> Job:
        return await self._repo.get_job(job_id)

    async def subscribe_run_events(
        self,
        *,
        last_event_id: str | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        async for event_id, event in self._run_event_stream.subscribe(
            last_event_id=last_event_id,
        ):
            yield event_id, event

    async def list_jobs(self, thread_id: str | None = None) -> list[Job]:
        return await self._repo.list_jobs(thread_id)

    async def delete_job(self, job_id: str) -> Job:
        job = await self._repo.get_job(job_id)
        await self._remove_job_resources(job)
        job = await self._repo.delete_job(job_id)
        return job

    async def _remove_job_resources(self, job: Job) -> None:
        if job.trigger_type == "time":
            await self._schedule_manager.remove_job(job.id)
        if job.subscription_id:
            await self._runtime_client.remove_subscription(
                subscription_id=job.subscription_id,
            )

    async def _remove_subscription_after_create_failure(self, subscription_id: str) -> None:
        try:
            await self._runtime_client.remove_subscription(subscription_id=subscription_id)
        except Exception as exc:
            logger.warning(
                "Failed to remove runtime subscription %s after job creation failed: %s",
                subscription_id,
                exc,
            )

    async def _cleanup_created_job_after_create_failure(self, job: Job) -> None:
        try:
            await self._remove_job_resources(job)
        except Exception as exc:
            logger.warning("Failed to clean external resources for job %s: %s", job.id, exc)
        try:
            await self._repo.delete_job(job.id)
        except Exception as exc:
            logger.warning("Failed to delete job %s after creation failed: %s", job.id, exc)

    async def run_job_now(self, job_id: str) -> dict[str, Any]:
        await self._repo.get_job(job_id)
        try:
            task = await run_job_task.kiq(
                job_id=job_id,
                trigger={"source": "manual"},
            )
            task_result = await task.wait_result(
                timeout=float(self._settings.job_task_timeout_seconds),
            )
        except TaskiqResultTimeoutError:
            return {"ok": False, "error": "Job task timed out."}
        except Exception as exc:
            logger.error("Failed to enqueue or await job task %s: %s", job_id, exc)
            return {"ok": False, "error": str(exc)}

        if task_result.is_err:
            error = task_result.error
            return {"ok": False, "error": str(error) if error else "Job task failed."}

        value = task_result.return_value
        if isinstance(value, dict):
            return value
        return {"ok": True, "response": value}

    def _validate_request(self, request: CreateJobRequest) -> None:
        if request.job_type == "analysis":
            if not request.analysis_code or not request.analysis_code.strip():
                raise ValueError("analysis jobs require analysis_code")
        else:
            if not request.prompt or not request.prompt.strip():
                raise ValueError("prompt jobs require prompt")

        if request.trigger_type == "time":
            if request.run_at is None and request.interval_seconds is None:
                raise ValueError("time jobs require run_at or interval_seconds")
            return

        if not request.thing_id:
            raise ValueError("event jobs require thing_id")
        if not request.event_name:
            raise ValueError("event jobs require event_name")
