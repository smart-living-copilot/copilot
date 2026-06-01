from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from taskiq.exceptions import TaskiqResultTimeoutError

from copilot.core.settings import Settings
from copilot.jobs.models import (
    CreateJobRequest,
    Job,
    JobActionKind,
    JobRun,
    JobRunStatus,
    JobTriggerKind,
    TimeTriggerKind,
    UpdateJobRequest,
)
from copilot.jobs.results import JobRunEventStream
from copilot.jobs.schedule import JobScheduleManager, build_schedule_source
from copilot.jobs.store import JobNotWaitingForInput, JobStore, utc_now
from copilot.jobs.subscriptions import subscription_id_from_response
from copilot.clients.wot_runtime import WotRuntimeClient
from copilot.jobs.taskiq_app import broker, run_job_task

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
        stale_after_seconds = getattr(
            self._settings,
            "job_run_stale_after_seconds",
            max(self._settings.job_task_timeout_seconds * 2, 600),
        )
        cutoff = utc_now() - timedelta(seconds=stale_after_seconds)
        stale_count = await self._repo.mark_stale_running_runs_failed(cutoff=cutoff)
        if stale_count:
            logger.warning("Marked %d stale job run(s) failed on startup", stale_count)
        await self._schedule_manager.sync()

    async def stop(self) -> None:
        await broker.shutdown()

    async def create_job(self, request: CreateJobRequest) -> Job:
        self._validate_request(request)

        next_run_at = None
        subscription_id = None
        if request.trigger_kind == JobTriggerKind.TIME:
            if request.schedule_kind == TimeTriggerKind.ONCE:
                next_run_at = request.run_at
            elif request.schedule_kind == TimeTriggerKind.INTERVAL:
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

        if job.trigger_kind == JobTriggerKind.TIME:
            try:
                await self._schedule_manager.add_job(job)
            except Exception:
                await self._cleanup_created_job_after_create_failure(job)
                raise
        return job

    async def get_job(self, job_id: str) -> Job:
        return await self._repo.get_job(job_id)

    async def get_job_by_thread_id(self, job_thread_id: str) -> Job:
        return await self._repo.get_job_by_thread_id(job_thread_id)

    async def subscribe_run_events(
        self,
        *,
        last_event_id: str | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        async for event_id, event in self._run_event_stream.subscribe(
            last_event_id=last_event_id,
        ):
            yield event_id, event

    async def list_jobs(self, created_from_thread_id: str | None = None) -> list[Job]:
        return await self._repo.list_jobs(created_from_thread_id)

    async def list_job_runs(self, job_id: str) -> list[JobRun]:
        await self._repo.get_job(job_id)
        return await self._repo.list_job_runs(job_id)

    async def update_job(self, job_id: str, request: UpdateJobRequest) -> Job:
        job = await self._repo.get_job(job_id)
        fields = request.model_dump(exclude_unset=True)
        self._validate_update(job, fields)

        if not fields:
            return job

        updated = await self._repo.update_job(job_id, **fields)

        if updated.trigger_kind == JobTriggerKind.TIME:
            await self._schedule_manager.remove_job(updated.id)
            if updated.enabled:
                await self._schedule_manager.add_job(updated)
        return updated

    def _validate_update(self, job: Job, fields: dict[str, Any]) -> None:
        if "prompt" in fields:
            if job.action_kind != JobActionKind.PROMPT:
                raise ValueError("prompt can only be set on prompt jobs")
            if not fields["prompt"] or not str(fields["prompt"]).strip():
                raise ValueError("prompt jobs require a non-empty prompt")
        if "analysis_code" in fields:
            if job.action_kind != JobActionKind.ANALYSIS:
                raise ValueError("analysis_code can only be set on analysis jobs")
            if not fields["analysis_code"] or not str(fields["analysis_code"]).strip():
                raise ValueError("analysis jobs require non-empty analysis_code")
        if "interval_seconds" in fields:
            if job.trigger_kind != JobTriggerKind.TIME or job.schedule_kind != TimeTriggerKind.INTERVAL:
                raise ValueError("interval_seconds can only be set on interval jobs")
        if "run_at" in fields:
            if job.trigger_kind != JobTriggerKind.TIME or job.schedule_kind != TimeTriggerKind.ONCE:
                raise ValueError("run_at can only be set on one-time jobs")

    async def cancel_job_run(self, job_id: str) -> Job:
        return await self._repo.cancel_active_run(job_id)

    async def delete_job(self, job_id: str) -> Job:
        job = await self._repo.get_job(job_id)
        await self._remove_job_resources(job)
        job = await self._repo.delete_job(job_id)
        return job

    async def _remove_job_resources(self, job: Job) -> None:
        if job.trigger_kind == JobTriggerKind.TIME:
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
            task = await self._enqueue_manual_run(job_id)
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

    async def reply_to_job(self, job_id: str, message: str) -> dict[str, Any]:
        job = await self._repo.get_job(job_id)
        if job.last_run_status != JobRunStatus.WAITING_FOR_INPUT:
            raise JobNotWaitingForInput(job_id)

        try:
            task = await run_job_task.kiq(
                job_id=job_id,
                trigger={
                    "source": "user_reply",
                    "message": message,
                    "previous_run_id": job.active_run_id or job.last_run_id,
                },
            )
            task_result = await task.wait_result(
                timeout=float(self._settings.job_task_timeout_seconds),
            )
        except TaskiqResultTimeoutError:
            return {"ok": False, "error": "Job task timed out."}
        except JobNotWaitingForInput:
            raise
        except Exception as exc:
            logger.error("Failed to enqueue or await job reply task %s: %s", job_id, exc)
            return {"ok": False, "error": str(exc)}

        if task_result.is_err:
            error = task_result.error
            if isinstance(error, JobNotWaitingForInput):
                raise error
            return {"ok": False, "error": str(error) if error else "Job task failed."}

        value = task_result.return_value
        if isinstance(value, dict):
            return value
        return {"ok": True, "response": value}

    async def reply_to_waiting_thread(
        self,
        thread_id: str,
        message: str,
    ) -> dict[str, Any] | None:
        try:
            job = await self._repo.get_job_by_thread_id(thread_id)
        except KeyError:
            return None

        if job.last_run_status != JobRunStatus.WAITING_FOR_INPUT:
            return None
        return await self.reply_to_job(job.id, message)

    async def trigger_job_now(self, job_id: str) -> dict[str, Any]:
        await self._repo.get_job(job_id)
        try:
            task = await self._enqueue_manual_run(job_id)
        except Exception as exc:
            logger.error("Failed to enqueue job task %s: %s", job_id, exc)
            raise RuntimeError(str(exc)) from exc

        task_id = getattr(task, "task_id", None)
        result: dict[str, Any] = {"ok": True, "job_id": job_id}
        if task_id is not None:
            result["task_id"] = str(task_id)
        return result

    async def _enqueue_manual_run(self, job_id: str) -> Any:
        return await run_job_task.kiq(
            job_id=job_id,
            trigger={"source": "manual"},
        )

    def _validate_request(self, request: CreateJobRequest) -> None:
        if request.action_kind == JobActionKind.ANALYSIS:
            if not request.analysis_code or not request.analysis_code.strip():
                raise ValueError("analysis jobs require analysis_code")
        else:
            if not request.prompt or not request.prompt.strip():
                raise ValueError("prompt jobs require prompt")

        if request.trigger_kind == JobTriggerKind.TIME:
            if request.schedule_kind is None:
                raise ValueError("time jobs require schedule_kind")
            if request.schedule_kind == TimeTriggerKind.ONCE:
                if request.run_at is None or request.interval_seconds is not None:
                    raise ValueError("one-time jobs require run_at only")
            elif request.schedule_kind == TimeTriggerKind.INTERVAL:
                if request.interval_seconds is None or request.run_at is not None:
                    raise ValueError("interval jobs require interval_seconds only")
            return

        if request.schedule_kind is not None or request.run_at is not None or request.interval_seconds is not None:
            raise ValueError("event jobs cannot include time schedule fields")

        if not request.thing_id:
            raise ValueError("event jobs require thing_id")
        if not request.event_name:
            raise ValueError("event jobs require event_name")
