from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta

import redis.asyncio as redis

from job_runner.code_executor_client import CodeExecutorClient
from job_runner.copilot_client import CopilotClient
from job_runner.models import CreateJobRequest, Job
from job_runner.runtime_client import WotRuntimeClient
from job_runner.settings import Settings
from job_runner.storage import JobRepository, utc_now
from job_runner.stream import StreamConfig, ensure_stream_group, parse_runtime_stream_fields

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._repo = JobRepository(settings.jobs_db_path)
        self._runtime_client = WotRuntimeClient(settings)
        self._copilot_client = CopilotClient(settings)
        self._code_executor_client = CodeExecutorClient(settings)
        self._stop_event = asyncio.Event()
        self._time_task: asyncio.Task[None] | None = None
        self._stream_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._repo.init()
        await self._sync_event_subscriptions()
        self._time_task = asyncio.create_task(self._run_time_scheduler())
        self._stream_task = asyncio.create_task(self._run_event_consumer())

    async def stop(self) -> None:
        self._stop_event.set()
        tasks = [task for task in (self._time_task, self._stream_task) if task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

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
            subscription_id = await self._runtime_client.subscribe_event(
                thing_id=request.thing_id or "",
                event_name=request.event_name or "",
                subscription_input=request.subscription_input,
            )

        return await self._repo.create_job(
            request,
            next_run_at=next_run_at,
            subscription_id=subscription_id,
        )

    async def list_jobs(self, thread_id: str | None = None) -> list[Job]:
        return await self._repo.list_jobs(thread_id)

    async def delete_job(self, job_id: str) -> Job:
        job = await self._repo.delete_job(job_id)
        if job.subscription_id:
            try:
                await self._runtime_client.remove_subscription(job.subscription_id)
            except Exception as exc:
                logger.warning("Failed to remove runtime subscription for job %s: %s", job_id, exc)
        return job

    async def run_job_now(self, job_id: str) -> dict:
        job = await self._repo.get_job(job_id)
        result = await self._dispatch_job(job, trigger={"source": "manual"})
        await self._repo.mark_manual_job_result(
            job_id=job.id,
            now=utc_now(),
            success=bool(result.get("ok")),
            error=result.get("error"),
            response_text=result.get("assistant"),
            last_fetch_value=result.get("last_fetch_value"),
        )
        return result

    def _validate_request(self, request: CreateJobRequest) -> None:
        if request.job_type == "analysis":
            if not request.analysis_code or not request.analysis_code.strip():
                raise ValueError("analysis jobs require analysis_code")
            if request.trigger_type != "time":
                raise ValueError("analysis jobs currently support only time triggers")
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

    async def _sync_event_subscriptions(self) -> None:
        jobs = await self._repo.list_enabled_event_jobs()
        for job in jobs:
            try:
                new_subscription_id = await self._runtime_client.subscribe_event(
                    thing_id=job.thing_id or "",
                    event_name=job.event_name or "",
                    subscription_input=job.subscription_input,
                )
                if job.subscription_id and job.subscription_id != new_subscription_id:
                    try:
                        await self._runtime_client.remove_subscription(job.subscription_id)
                    except Exception:
                        pass
                await self._repo.set_subscription_id(job.id, new_subscription_id)
            except Exception as exc:
                logger.error("Failed to sync subscription for job %s: %s", job.id, exc)

    async def _run_time_scheduler(self) -> None:
        while not self._stop_event.is_set():
            now = utc_now()
            due_jobs = await self._repo.list_due_time_jobs(now=now)
            for job in due_jobs:
                result = await self._dispatch_job(job, trigger={"source": "time"})
                await self._repo.mark_time_job_result(
                    job=job,
                    now=utc_now(),
                    success=bool(result.get("ok")),
                    error=result.get("error"),
                    response_text=result.get("assistant"),
                    last_fetch_value=result.get("last_fetch_value"),
                )
            await asyncio.sleep(self._settings.scheduler_poll_seconds)

    async def _run_event_consumer(self) -> None:
        cfg = StreamConfig(
            stream=self._settings.wot_runtime_stream,
            group=self._settings.jobs_events_group,
            consumer=self._settings.jobs_events_consumer,
            batch_size=self._settings.jobs_stream_batch_size,
            poll_block_ms=self._settings.jobs_stream_poll_block_ms,
            claim_idle_ms=self._settings.jobs_stream_claim_idle_ms,
        )

        while not self._stop_event.is_set():
            redis_client = None
            try:
                redis_client = redis.from_url(self._settings.redis_url, decode_responses=True)
                await ensure_stream_group(redis_client, stream=cfg.stream, group=cfg.group)

                while not self._stop_event.is_set():
                    stale_entries = await self._claim_stale_entries(redis_client, cfg)
                    if stale_entries:
                        for entry_id, fields in stale_entries:
                            await self._handle_stream_entry(fields)
                            await redis_client.xack(cfg.stream, cfg.group, entry_id)
                        continue

                    records = await redis_client.xreadgroup(
                        groupname=cfg.group,
                        consumername=cfg.consumer,
                        streams={cfg.stream: ">"},
                        count=cfg.batch_size,
                        block=cfg.poll_block_ms,
                    )
                    if not records:
                        continue

                    for _stream_name, entries in records:
                        for entry_id, fields in entries:
                            await self._handle_stream_entry(fields)
                            await redis_client.xack(cfg.stream, cfg.group, entry_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Event stream loop failed: %s", exc)
                await asyncio.sleep(2)
            finally:
                if redis_client is not None:
                    await redis_client.aclose()

    async def _claim_stale_entries(
        self,
        redis_client: redis.Redis,
        cfg: StreamConfig,
    ) -> list[tuple[str, dict[str, str]]]:
        next_start = "0-0"
        claimed: list[tuple[str, dict[str, str]]] = []

        while True:
            next_start, entries, _deleted = await redis_client.xautoclaim(
                cfg.stream,
                cfg.group,
                cfg.consumer,
                cfg.claim_idle_ms,
                start_id=next_start,
                count=cfg.batch_size,
            )
            if entries:
                claimed.extend(entries)
            if next_start == "0-0" or not entries:
                break

        return claimed

    async def _handle_stream_entry(self, fields: dict[str, str]) -> None:
        event = parse_runtime_stream_fields(fields)
        if event["event_type"] != "event_received":
            return

        subscription_id = event.get("subscription_id")
        if not subscription_id:
            return

        jobs = await self._repo.list_event_jobs_for_subscription(subscription_id)
        if not jobs:
            return

        for job in jobs:
            result = await self._dispatch_job(
                job,
                trigger={
                    "source": "wot_event",
                    "thing_id": event.get("thing_id"),
                    "event_name": event.get("name"),
                    "content_type": event.get("content_type"),
                    "payload_base64": event.get("payload_base64"),
                    "timestamp": event.get("timestamp"),
                },
            )
            await self._repo.mark_event_job_result(
                job_id=job.id,
                now=utc_now(),
                success=bool(result.get("ok")),
                error=result.get("error"),
                response_text=result.get("assistant"),
                last_fetch_value=result.get("last_fetch_value"),
            )

    async def _dispatch_job(self, job: Job, *, trigger: dict) -> dict:
        if job.job_type == "analysis":
            return await self._run_analysis_job(job, trigger=trigger)
        return await self._run_prompt_job(job, trigger=trigger)

    async def _run_prompt_job(self, job: Job, *, trigger: dict) -> dict:
        try:
            response = await self._copilot_client.dispatch_prompt(
                thread_id=job.thread_id,
                prompt=job.prompt or "",
                metadata={"job_id": job.id, "trigger": trigger},
            )
            assistant = response.get("assistant") if isinstance(response, dict) else None
            if not assistant:
                if isinstance(response, dict):
                    assistant = json.dumps(response, ensure_ascii=True)[:2000]
                else:
                    assistant = str(response)[:2000]
            return {"ok": True, "response": response, "assistant": assistant}
        except Exception as exc:
            logger.error("Failed dispatch for job %s: %s", job.id, exc)
            return {"ok": False, "error": str(exc)}

    async def _run_analysis_job(self, job: Job, *, trigger: dict) -> dict:
        try:
            response = await self._code_executor_client.execute(
                session_id=f"job-analysis:{job.id}",
                code=job.analysis_code or "",
            )
            stdout = str(response.get("stdout", "")).strip()
            images = response.get("images", [])
            plotly = response.get("plotly", [])
            last_fetch_value = self._extract_last_fetch_value(response)

            parts: list[str] = []
            if stdout:
                parts.append(stdout)
            if images:
                parts.append(f"images={len(images)}")
            if plotly:
                parts.append(f"plotly={len(plotly)}")
            if not parts:
                parts.append("(no output)")

            return {
                "ok": True,
                "response": response,
                "assistant": "\n".join(parts)[:4000],
                "last_fetch_value": last_fetch_value,
                "metadata": {"trigger": trigger},
            }
        except Exception as exc:
            logger.error("Failed analysis job %s: %s", job.id, exc)
            return {"ok": False, "error": str(exc)}

    def _extract_last_fetch_value(self, response: dict) -> str | None:
        """Best-effort extraction of a meaningful latest value from analysis output."""
        stdout = str(response.get("stdout", "") or "").strip()
        if not stdout:
            return None

        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines:
            return None

        last_line = lines[-1]
        marker = "WOT_LAST_VALUE="
        if last_line.startswith(marker):
            return last_line[len(marker) :][:500]

        try:
            payload = json.loads(last_line)
            if isinstance(payload, dict):
                for key in ("last_fetch_value", "last_value", "value", "wot_value"):
                    if key in payload:
                        return str(payload[key])[:500]
        except Exception:
            pass

        return last_line[:500]
