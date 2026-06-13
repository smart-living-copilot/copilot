from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from taskiq.exceptions import TaskiqResultTimeoutError

from copilot.clients.wot_runtime import WotRuntimeClient
from copilot.core.settings import Settings
from copilot.jobs.enums import JobRunStatus
from copilot.jobs.records import VirtualRecordStore
from copilot.jobs.resources import JobResourceManager
from copilot.jobs.results import JobRunEventStream
from copilot.jobs.schedule import JobScheduleManager, build_schedule_source
from copilot.jobs.schemas import CreateJobRequest, Job, JobRun, JobRunEvent, UpdateJobRequest
from copilot.jobs.stores import JobNotWaitingForInput, JobStore, utc_now
from copilot.jobs.taskiq_app import broker, run_job_task

logger = logging.getLogger(__name__)


class JobService:
    """Application facade for job validation, persistence, resources, and runs."""

    def __init__(
        self,
        settings: Settings,
        *,
        repo: JobStore | None = None,
        runtime_client: WotRuntimeClient | None = None,
        run_event_stream: JobRunEventStream | None = None,
        schedule_manager: JobScheduleManager | None = None,
        record_store: VirtualRecordStore | None = None,
    ) -> None:
        self._settings = settings
        self._repo = repo or JobStore()
        self._run_event_stream = run_event_stream or JobRunEventStream(settings)
        runtime_client = runtime_client or WotRuntimeClient(settings)
        schedule_manager = schedule_manager or JobScheduleManager(
            build_schedule_source(settings),
            repo=self._repo,
        )
        record_store = record_store or VirtualRecordStore()
        self._resources = JobResourceManager(
            repo=self._repo,
            runtime_client=runtime_client,
            schedule_manager=schedule_manager,
            record_store=record_store,
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
        await self._resources.sync()

    async def stop(self) -> None:
        await broker.shutdown()

    async def create_job(self, request: CreateJobRequest) -> Job:
        request = request.normalized_request(
            default_cron_timezone=self._settings.jobs_default_timezone
        )
        return await self._resources.create_job(request)

    async def get_job(self, job_id: str) -> Job:
        return await self._repo.get_job(job_id)

    async def get_job_by_thread_id(self, job_thread_id: str) -> Job:
        return await self._repo.get_job_by_thread_id_any(job_thread_id)

    async def get_active_or_last_job_run(self, job_id: str) -> JobRun:
        return await self._repo.get_active_or_last_job_run(job_id)

    async def get_latest_job_run(self, job_id: str) -> JobRun | None:
        return await self._repo.get_latest_job_run(job_id)

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

    async def list_job_runs(
        self,
        job_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JobRun]:
        await self._repo.get_job(job_id)
        return await self._repo.list_job_runs(job_id, limit=limit, offset=offset)

    async def list_job_run_page(
        self,
        job_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[JobRun], int]:
        await self._repo.get_job(job_id)
        total = await self._repo.count_job_runs(job_id)
        runs = await self._repo.list_job_runs(job_id, limit=limit, offset=offset)
        return runs, total

    async def list_job_run_events(self, job_id: str) -> list[JobRunEvent]:
        await self._repo.get_job(job_id)
        return await self._repo.list_job_run_events(job_id)

    async def update_job(self, job_id: str, request: UpdateJobRequest) -> Job:
        previous = await self._repo.get_job(job_id)
        updated = previous

        metadata_fields: dict[str, Any] = {}
        if request.name is not None:
            metadata_fields["name"] = request.name
        if request.enabled is not None:
            metadata_fields["enabled"] = request.enabled
        if metadata_fields:
            updated = await self._repo.update_job_metadata(job_id, **metadata_fields)

        if request.definition is not None:
            definition = request.definition.normalized(
                name=updated.name,
                default_cron_timezone=self._settings.jobs_default_timezone,
            )
            prepared = await self._resources.prepare_definition(
                definition,
                enabled=updated.enabled,
            )
            try:
                updated = await self._repo.replace_job_definition(
                    job_id,
                    definition,
                    next_run_at=prepared.next_run_at,
                    subscription_id=prepared.subscription_id,
                )
            except Exception:
                await self._resources.cleanup_prepared_create(prepared)
                raise

        if updated == previous:
            return previous
        return await self._resources.update_job_resources(previous, updated)

    async def cancel_job_run(self, job_id: str) -> Job:
        return await self._repo.cancel_active_run(job_id)

    async def delete_job(self, job_id: str) -> Job:
        return await self._resources.delete_job(job_id)

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

    async def reply_to_job(
        self,
        job_id: str,
        message: str,
        *,
        client_reply_id: str | None = None,
    ) -> dict[str, Any]:
        job = await self._repo.get_job(job_id)
        client_reply_id = _normalize_client_reply_id(client_reply_id)
        if job.last_run_status != JobRunStatus.WAITING_FOR_INPUT:
            if client_reply_id:
                duplicate_run = await self._repo.get_job_run_by_client_reply_id(
                    job_id,
                    client_reply_id,
                )
                if duplicate_run is not None:
                    return _duplicate_reply_result(duplicate_run)
            raise JobNotWaitingForInput(job_id)

        try:
            task = await run_job_task.kiq(
                job_id=job_id,
                trigger={
                    "source": "user_reply",
                    "message": message,
                    "client_reply_id": client_reply_id,
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
            job = await self._repo.get_job_by_thread_id_any(thread_id)
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


def _normalize_client_reply_id(client_reply_id: str | None) -> str | None:
    normalized = (client_reply_id or "").strip()
    return normalized or None


def _duplicate_reply_result(run: JobRun) -> dict[str, Any]:
    result = run.result if isinstance(run.result, dict) else None
    return {
        "ok": True,
        "status": "duplicate_reply",
        "run": run.model_dump(mode="json"),
        "result": result,
    }
