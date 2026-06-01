from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from copilot.core.api_dependencies import verify_internal_api_key
from copilot.jobs.models import CreateJobRequest, ReplyJobRequest, UpdateJobRequest
from copilot.jobs.store import JobNotWaitingForInput, JobRunNotCancellable
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
    return job.model_dump()


@router.get("/jobs")
async def list_jobs(
    request: Request,
    created_from_thread_id: str | None = Query(default=None),
):
    verify_internal_api_key(request)
    service = request.app.state.service
    jobs = await service.list_jobs(created_from_thread_id=created_from_thread_id)
    return {"jobs": [job.model_dump() for job in jobs]}


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
async def list_job_runs(job_id: str, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        runs = await service.list_job_runs(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    return {"runs": [run.model_dump() for run in runs]}


@router.get("/jobs/{job_id}/thread")
async def get_job_thread(job_id: str, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        job = await service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")

    record = await asyncio.to_thread(get_thread, job.job_thread_id)
    if record is None:
        raise HTTPException(status_code=404, detail="job thread not found")

    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer is None:
        raise HTTPException(status_code=503, detail="Checkpointer not ready")

    messages = await checkpoint_thread_messages(checkpointer, job.job_thread_id)
    return {**record, "job": job.model_dump(), "messages": messages}


@router.post("/jobs/{job_id}/reply")
async def reply_to_job(job_id: str, payload: ReplyJobRequest, request: Request):
    verify_internal_api_key(request)
    service = request.app.state.service
    try:
        return await service.reply_to_job(job_id, payload.message)
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
    return job.model_dump()


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
    return job.model_dump()


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
    return {"ok": True, "job": job.model_dump()}


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
    return {"ok": True, "job": job.model_dump()}


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
