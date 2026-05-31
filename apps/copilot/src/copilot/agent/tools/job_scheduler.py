"""LangChain tools for managing automation jobs via copilot's in-process JobService.

These tools only run inside the API-process agent graph (see ``LOCAL_TOOLS``), where the
``JobService`` singleton is registered with ``set_active_job_service``. They therefore call
it directly instead of round-tripping through the HTTP job API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import ValidationError

from copilot.jobs.active import get_active_job_service
from copilot.jobs.models import CreateJobRequest, JobActionKind

if TYPE_CHECKING:
    from copilot.jobs.service import JobService

_SERVICE_UNAVAILABLE = {"error": "Job runner is not enabled"}


def _thread_id_from_config(
    config: RunnableConfig,
    created_from_thread_id: str | None,
) -> str:
    return created_from_thread_id or config.get("configurable", {}).get("thread_id", "default")


async def _run_job(service: JobService, job_id: str) -> dict[str, Any]:
    try:
        return await service.run_job_now(job_id)
    except KeyError:
        return {"ok": False, "error": "job not found"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def _create_job(
    service: JobService,
    request: CreateJobRequest,
) -> dict[str, Any]:
    try:
        job = await service.create_job(request)
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}

    return job.model_dump(mode="json")


@tool
async def create_job(
    name: str,
    prompt: str,
    trigger_kind: str,
    config: RunnableConfig,
    schedule_kind: str | None = None,
    created_from_thread_id: str | None = None,
    run_at: str | None = None,
    interval_seconds: int | None = None,
    thing_id: str | None = None,
    event_name: str | None = None,
    subscription_input: Any = None,
) -> dict[str, Any]:
    """Create an automation job.

    trigger_kind:
    - "time": use run_at (ISO datetime) or interval_seconds
    - "event": use thing_id and event_name

    schedule_kind:
    - "once": run one time at run_at
    - "interval": run every interval_seconds
    """
    service = get_active_job_service()
    if service is None:
        return dict(_SERVICE_UNAVAILABLE)
    try:
        request = CreateJobRequest(
            name=name,
            created_from_thread_id=_thread_id_from_config(config, created_from_thread_id),
            prompt=prompt,
            trigger_kind=trigger_kind,
            schedule_kind=schedule_kind,
            run_at=run_at,
            interval_seconds=interval_seconds,
            thing_id=thing_id,
            event_name=event_name,
            subscription_input=subscription_input,
        )
    except ValidationError as exc:
        return {"error": str(exc)}
    return await _create_job(service, request)


@tool
async def create_analysis_job(
    name: str,
    analysis_code: str,
    trigger_kind: str,
    config: RunnableConfig,
    schedule_kind: str | None = None,
    created_from_thread_id: str | None = None,
    run_at: str | None = None,
    interval_seconds: int | None = None,
    thing_id: str | None = None,
    event_name: str | None = None,
    subscription_input: Any = None,
) -> dict[str, Any]:
    """Create an analysis job that runs Python in the code-executor sandbox.

    trigger_kind:
    - "time": use run_at (one-time ISO datetime) or interval_seconds (recurring cadence)
    - "event": use thing_id and event_name to run on a subscribed WoT event

    schedule_kind:
    - "once": run one time at run_at
    - "interval": run every interval_seconds
    """
    service = get_active_job_service()
    if service is None:
        return dict(_SERVICE_UNAVAILABLE)
    try:
        request = CreateJobRequest(
            name=name,
            created_from_thread_id=_thread_id_from_config(config, created_from_thread_id),
            action_kind=JobActionKind.ANALYSIS,
            analysis_code=analysis_code,
            trigger_kind=trigger_kind,
            schedule_kind=schedule_kind,
            run_at=run_at,
            interval_seconds=interval_seconds,
            thing_id=thing_id,
            event_name=event_name,
            subscription_input=subscription_input,
        )
    except ValidationError as exc:
        return {"error": str(exc)}
    return await _create_job(service, request)


@tool
async def list_jobs(created_from_thread_id: str | None = None) -> dict[str, Any]:
    """List automation jobs, optionally filtered by creating chat thread.

    If created_from_thread_id is omitted, returns all jobs.
    """
    service = get_active_job_service()
    if service is None:
        return dict(_SERVICE_UNAVAILABLE)
    jobs = await service.list_jobs(created_from_thread_id=created_from_thread_id)
    return {"jobs": [job.model_dump(mode="json") for job in jobs]}


@tool
async def delete_job(job_id: str) -> dict[str, Any]:
    """Delete an automation job by id."""
    service = get_active_job_service()
    if service is None:
        return dict(_SERVICE_UNAVAILABLE)
    try:
        job = await service.delete_job(job_id)
    except KeyError:
        return {"error": "job not found"}
    except Exception as exc:
        return {"error": str(exc)}
    return {"ok": True, "job": job.model_dump(mode="json")}


@tool
async def run_job_now(job_id: str) -> dict[str, Any]:
    """Trigger an automation job immediately and return the execution result."""
    service = get_active_job_service()
    if service is None:
        return dict(_SERVICE_UNAVAILABLE)
    return await _run_job(service, job_id)
