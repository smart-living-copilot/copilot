from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from copilot.core.api_dependencies import verify_internal_api_key
from copilot.jobs.enums import JobRunEventType
from copilot.jobs.schemas import (
    CreateJobRequest,
    JobRunEvent,
    ReplyJobRequest,
    UpdateJobRequest,
)
from copilot.jobs.record_summary import submitted_record_event_message
from copilot.jobs.stores import JobNotWaitingForInput, JobRunNotCancellable
from copilot.threads.messages import checkpoint_thread_messages
from copilot.threads.store import get_thread

router = APIRouter()


@router.post("/jobs")
async def create_job(payload: CreateJobRequest, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        job = await service.create_job(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return job.model_dump(mode="json", by_alias=True)


@router.get("/jobs")
async def list_jobs(
    request: Request,
    created_from_thread_id: str | None = Query(default=None),
):
    verify_internal_api_key(request)
    service = request.app.state.service
    jobs = await service.list_jobs(created_from_thread_id=created_from_thread_id)
    return {"jobs": [job.model_dump(mode="json", by_alias=True) for job in jobs]}


@router.get("/jobs/events")
async def stream_job_events(request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    last_event_id = request.headers.get("last-event-id")

    async def event_stream():
        yield ": connected\n\n"
        async for event_id, event in service.subscribe_run_events(last_event_id=last_event_id):
            if await request.is_disconnected():
                break
            payload = json.dumps(event, ensure_ascii=True)
            yield f"id: {event_id}\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/jobs/{job_id}/runs")
async def list_job_runs(
    job_id: str,
    request: Request,
    limit: int = Query(default=5, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        runs, total = await service.list_job_run_page(
            job_id,
            limit=limit,
            offset=offset,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "runs": [run.model_dump() for run in runs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/jobs/{job_id}/run-events")
async def list_job_run_events(job_id: str, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        events = await service.list_job_run_events(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    return {"events": [event.model_dump(mode="json") for event in events]}


@router.get("/jobs/{job_id}/thread")
async def get_job_thread(job_id: str, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        job = await service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")

    run = None
    try:
        run = await service.get_active_or_last_job_run(job_id)
    except KeyError:
        pass

    thread_id = run.job_thread_id if run is not None else job.job_thread_id
    record = await asyncio.to_thread(get_thread, thread_id)
    if record is None:
        record = {
            "id": thread_id,
            "title": f"Job: {job.name}",
            "createdAt": job.created_at.isoformat(),
            "updatedAt": job.updated_at.isoformat(),
            "kind": "job",
            "visible": False,
            "jobId": job.id,
        }

    events = await service.list_job_run_events(job_id)
    messages = _messages_from_job_run_events(events)
    if not messages:
        checkpointer = getattr(request.app.state, "checkpointer", None)
        if checkpointer is not None:
            messages = await checkpoint_thread_messages(checkpointer, thread_id)
    return {
        **record,
        "job": job.model_dump(mode="json", by_alias=True),
        "run": run.model_dump() if run is not None else None,
        "events": [event.model_dump(mode="json") for event in events],
        "messages": messages,
    }


@router.post("/jobs/{job_id}/reply")
async def reply_to_job(job_id: str, payload: ReplyJobRequest, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        return await service.reply_to_job(
            job_id,
            payload.message,
            client_reply_id=payload.client_reply_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except JobNotWaitingForInput as exc:
        raise HTTPException(status_code=409, detail="job is not waiting for input") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        job = await service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump(mode="json", by_alias=True)


@router.patch("/jobs/{job_id}")
async def update_job(job_id: str, payload: UpdateJobRequest, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        job = await service.update_job(job_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return job.model_dump(mode="json", by_alias=True)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        job = await service.cancel_job_run(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except JobRunNotCancellable as exc:
        raise HTTPException(status_code=409, detail="job has no active run to cancel") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "job": job.model_dump(mode="json", by_alias=True)}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        job = await service.delete_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "job": job.model_dump(mode="json", by_alias=True)}


@router.post("/jobs/{job_id}/run", status_code=202)
async def run_job(job_id: str, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        result = await service.trigger_job_now(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result


def _messages_from_job_run_events(events: list[JobRunEvent]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for event in events:
        content = _message_content_from_event(event)
        if not content:
            continue
        messages.append(
            {
                "id": f"job-event-{event.id}",
                "role": _message_role_from_event(event.event_type),
                "content": content,
                "createdAt": event.created_at.isoformat(),
                "jobRunId": event.run_id,
                "jobEventType": event.event_type.value,
            }
        )
    return messages


def _message_role_from_event(event_type: JobRunEventType) -> str:
    if event_type == JobRunEventType.USER_REPLY:
        return "user"
    if event_type in {
        JobRunEventType.ASSISTANT_MESSAGE,
        JobRunEventType.WAITING_FOR_INPUT,
    }:
        return "assistant"
    return "system"


def _message_content_from_event(event: JobRunEvent) -> str:
    if event.event_type == JobRunEventType.RECORD_SUBMITTED:
        if event.message and event.message != "Structured record submitted.":
            return event.message
        return submitted_record_event_message(event.payload)
    if event.message:
        return event.message
    if event.event_type == JobRunEventType.RUN_STARTED:
        return "Run started."
    if event.event_type == JobRunEventType.RUN_SUCCEEDED:
        return "Run succeeded."
    if event.event_type == JobRunEventType.RUN_FAILED:
        return "Run failed."
    if event.event_type == JobRunEventType.RUN_CANCELLED:
        return "Run cancelled."
    if event.event_type == JobRunEventType.RUN_SKIPPED:
        return "Run skipped."
    return ""
