from __future__ import annotations

import logging

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from taskiq.exceptions import TaskiqResultTimeoutError

from copilot.core.settings import Settings
from copilot.jobs.cron import validate_cron_schedule
from copilot.jobs.enums import (
    JobActionKind,
    JobInteractionMode,
    JobOutputKind,
    JobRunStatus,
    JobTriggerKind,
    TimeTriggerKind,
)
from copilot.jobs.schemas import CreateJobRequest, Job, JobRun, JobRunEvent, UpdateJobRequest
from copilot.jobs.results import JobRunEventStream
from copilot.jobs.records import (
    VirtualRecordStore,
    make_virtual_record_thing_id,
    validate_record_schema,
)
from copilot.jobs.resources import JobResourceManager
from copilot.jobs.schedule import JobScheduleManager, build_schedule_source
from copilot.jobs.stores import JobNotWaitingForInput, JobStore, utc_now
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
        request = self._normalize_create_request(request)
        self._validate_request(request)
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
        job = await self._repo.get_job(job_id)
        fields = request.model_dump(exclude_unset=True)
        fields = self._normalize_update_fields(job, fields)
        self._validate_update(job, fields)

        if not fields:
            return job

        updated = await self._repo.update_job(job_id, **fields)
        return await self._resources.update_job_resources(job, updated)

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

        schedule_fields = {
            "schedule_kind",
            "interval_seconds",
            "run_at",
            "cron_expression",
            "cron_timezone",
        }
        if schedule_fields.intersection(fields):
            if job.trigger_kind != JobTriggerKind.TIME:
                raise ValueError("schedule fields can only be set on time jobs")
            schedule_kind = fields.get("schedule_kind", job.schedule_kind)
            if schedule_kind is None:
                raise ValueError("time jobs require schedule_kind")
            if schedule_kind == TimeTriggerKind.INTERVAL:
                interval_seconds = fields.get("interval_seconds", job.interval_seconds)
                if interval_seconds is None:
                    raise ValueError("interval jobs require interval_seconds")
            elif schedule_kind == TimeTriggerKind.ONCE:
                run_at = fields.get("run_at", job.run_at)
                if run_at is None:
                    raise ValueError("one-time jobs require run_at")
            elif schedule_kind == TimeTriggerKind.CRON:
                expression = fields.get("cron_expression", job.cron_expression)
                timezone_name = fields.get("cron_timezone", job.cron_timezone)
                validate_cron_schedule(
                    expression,
                    timezone_name or self._settings.jobs_default_timezone,
                )

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

    def _validate_request(self, request: CreateJobRequest) -> None:
        if request.action_kind == JobActionKind.ANALYSIS:
            if not request.analysis_code or not request.analysis_code.strip():
                raise ValueError("analysis jobs require analysis_code")
            if request.output_kind != JobOutputKind.NARRATIVE:
                raise ValueError("analysis jobs only support narrative output")
        else:
            if not request.prompt or not request.prompt.strip():
                raise ValueError("prompt jobs require prompt")
            if request.output_kind == JobOutputKind.STRUCTURED_RECORD:
                if request.interaction_mode == JobInteractionMode.AUTONOMOUS:
                    raise ValueError(
                        "structured record prompt jobs require a non-autonomous interaction mode"
                    )
                if not request.virtual_thing_id:
                    raise ValueError("structured record jobs require virtual_thing_id")
                validate_record_schema(request.record_schema)
            elif (
                request.record_schema is not None
                or request.record_schema_version is not None
                or request.virtual_thing_id is not None
                or request.virtual_thing_title is not None
                or request.virtual_thing_description is not None
            ):
                raise ValueError("record fields require output_kind='structured_record'")

        if request.trigger_kind == JobTriggerKind.TIME:
            if request.schedule_kind is None:
                raise ValueError("time jobs require schedule_kind")
            if request.schedule_kind == TimeTriggerKind.ONCE:
                if (
                    request.run_at is None
                    or request.interval_seconds is not None
                    or request.cron_expression is not None
                    or request.cron_timezone is not None
                ):
                    raise ValueError("one-time jobs require run_at only")
            elif request.schedule_kind == TimeTriggerKind.INTERVAL:
                if (
                    request.interval_seconds is None
                    or request.run_at is not None
                    or request.cron_expression is not None
                    or request.cron_timezone is not None
                ):
                    raise ValueError("interval jobs require interval_seconds only")
            elif request.schedule_kind == TimeTriggerKind.CRON:
                if (
                    request.cron_expression is None
                    or request.run_at is not None
                    or request.interval_seconds is not None
                ):
                    raise ValueError("cron jobs require cron_expression only")
                validate_cron_schedule(request.cron_expression, request.cron_timezone)
            return

        if (
            request.schedule_kind is not None
            or request.run_at is not None
            or request.interval_seconds is not None
            or request.cron_expression is not None
            or request.cron_timezone is not None
        ):
            raise ValueError("event jobs cannot include time schedule fields")

        if not request.thing_id:
            raise ValueError("event jobs require thing_id")
        if not request.event_name:
            raise ValueError("event jobs require event_name")

    def _normalize_create_request(self, request: CreateJobRequest) -> CreateJobRequest:
        fields: dict[str, Any] = {}
        if (
            request.trigger_kind == JobTriggerKind.TIME
            and request.schedule_kind == TimeTriggerKind.CRON
        ):
            expression, timezone_name = validate_cron_schedule(
                request.cron_expression,
                request.cron_timezone or self._settings.jobs_default_timezone,
            )
            fields["cron_expression"] = expression
            fields["cron_timezone"] = timezone_name
        if request.output_kind == JobOutputKind.STRUCTURED_RECORD:
            fields["record_schema"] = validate_record_schema(request.record_schema)
            fields["record_schema_version"] = request.record_schema_version or 1
            fields["virtual_thing_id"] = request.virtual_thing_id or make_virtual_record_thing_id(
                request.virtual_thing_title or request.name
            )
            if request.interaction_mode == JobInteractionMode.AUTONOMOUS:
                fields["interaction_mode"] = JobInteractionMode.REQUIRED_CHECKIN
        return request.model_copy(update=fields) if fields else request

    def _normalize_update_fields(self, job: Job, fields: dict[str, Any]) -> dict[str, Any]:
        if job.trigger_kind != JobTriggerKind.TIME:
            return fields

        normalized = dict(fields)
        schedule_kind = normalized.get("schedule_kind", job.schedule_kind)

        if "schedule_kind" in normalized:
            if schedule_kind == TimeTriggerKind.INTERVAL:
                normalized.setdefault("run_at", None)
                normalized.setdefault("cron_expression", None)
                normalized.setdefault("cron_timezone", None)
            elif schedule_kind == TimeTriggerKind.ONCE:
                normalized.setdefault("interval_seconds", None)
                normalized.setdefault("cron_expression", None)
                normalized.setdefault("cron_timezone", None)
            elif schedule_kind == TimeTriggerKind.CRON:
                normalized.setdefault("interval_seconds", None)
                normalized.setdefault("run_at", None)

        if schedule_kind != TimeTriggerKind.CRON:
            return normalized
        if not (
            "schedule_kind" in normalized
            or "cron_expression" in normalized
            or "cron_timezone" in normalized
        ):
            return normalized

        expression = normalized.get("cron_expression", job.cron_expression)
        timezone_name = normalized.get(
            "cron_timezone",
            job.cron_timezone or self._settings.jobs_default_timezone,
        )
        expression, timezone_name = validate_cron_schedule(
            expression,
            timezone_name or self._settings.jobs_default_timezone,
        )
        normalized["cron_expression"] = expression
        normalized["cron_timezone"] = timezone_name
        return normalized


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
