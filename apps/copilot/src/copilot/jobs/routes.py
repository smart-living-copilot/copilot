from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from copilot.jobs.models import CreateJobRequest
from copilot.jobs.service import JobService

router = APIRouter()


def _service(request: Request) -> JobService:
    service = getattr(request.app.state, "service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Job runner is not enabled")
    return service


def _verify_internal_api_key(request: Request) -> None:
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not settings.internal_api_key:
        return

    expected = f"Bearer {settings.internal_api_key}"
    if request.headers.get("authorization", "") != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


@router.post("/jobs")
async def create_job(payload: CreateJobRequest, request: Request):
    _verify_internal_api_key(request)
    service = _service(request)
    try:
        job = await service.create_job(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return job.model_dump()


@router.get("/jobs")
async def list_jobs(request: Request, thread_id: str | None = Query(default=None)):
    _verify_internal_api_key(request)
    service = _service(request)
    jobs = await service.list_jobs(thread_id=thread_id)
    return {"jobs": [job.model_dump() for job in jobs]}


@router.get("/jobs/events")
async def stream_job_events(request: Request):
    _verify_internal_api_key(request)
    service = _service(request)
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


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    _verify_internal_api_key(request)
    service = _service(request)
    try:
        job = await service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump()


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, request: Request):
    _verify_internal_api_key(request)
    service = _service(request)
    try:
        job = await service.delete_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "job": job.model_dump()}


@router.post("/jobs/{job_id}/run", status_code=202)
async def run_job(job_id: str, request: Request):
    _verify_internal_api_key(request)
    service = _service(request)
    try:
        result = await service.trigger_job_now(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result
