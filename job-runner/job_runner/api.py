from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from html import escape

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from job_runner.models import CreateJobRequest
from job_runner.service import JobService
from job_runner.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    logging.basicConfig(level=settings.log_level)

    service = JobService(settings)
    app.state.settings = settings
    app.state.service = service
    await service.start()
    try:
        yield
    finally:
        await service.stop()


app = FastAPI(title="Job Runner", lifespan=lifespan)


def _job_status(job, now: datetime) -> str:
    if not job.enabled:
        return "disabled"
    if job.trigger_type == "event":
        return "waiting-event"
    if job.next_run_at is None:
        return "queued"
    if job.next_run_at <= now:
        return "queued"
    return "scheduled"


def _fmt(value) -> str:
    if value is None:
        return "-"
    return escape(str(value))


def _render_jobs_table_rows(jobs: list, now: datetime) -> str:
    rows: list[str] = []
    for job in jobs:
        status = _job_status(job, now)
        answer = _fmt(job.last_response)
        rows.append(
            "<tr>"
            f"<td>{_fmt(job.name)}</td>"
            f"<td><code>{_fmt(job.id)}</code></td>"
            f"<td>{_fmt(status)}</td>"
            f"<td>{_fmt(job.trigger_type)}</td>"
            f"<td>{_fmt(job.next_run_at)}</td>"
            f"<td>{_fmt(job.last_run_at)}</td>"
            f"<td>{_fmt(job.last_error)}</td>"
            f"<td class='answer'>{answer}</td>"
            "</tr>"
        )
    if not rows:
        return "<tr><td colspan='8'>No jobs yet.</td></tr>"
    return "".join(rows)


def _verify_internal_api_key(request: Request) -> None:
    settings: Settings = app.state.settings
    if not settings.internal_api_key:
        return

    expected = f"Bearer {settings.internal_api_key}"
    if request.headers.get("authorization", "") != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ui", response_class=HTMLResponse)
async def ui(request: Request):
        service: JobService = app.state.service
        jobs = await service.list_jobs()
        now = datetime.now(timezone.utc)

        queued = sum(1 for j in jobs if _job_status(j, now) == "queued")
        scheduled = sum(1 for j in jobs if _job_status(j, now) == "scheduled")
        waiting_event = sum(1 for j in jobs if _job_status(j, now) == "waiting-event")

        rows_html = _render_jobs_table_rows(jobs, now)

        html = f"""
<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Job Runner UI</title>
    <style>
        body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; margin: 24px; }}
        h1 {{ margin: 0 0 8px; }}
        .muted {{ color: #666; margin-bottom: 16px; }}
        .stats {{ display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }}
        .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 10px 14px; min-width: 120px; }}
        .label {{ font-size: 12px; color: #666; }}
        .value {{ font-size: 22px; font-weight: 700; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; text-align: left; padding: 8px; vertical-align: top; }}
        th {{ background: #f7f7f7; position: sticky; top: 0; }}
        code {{ font-size: 12px; }}
        .answer {{ white-space: pre-wrap; max-width: 560px; }}
    </style>
</head>
<body>
    <h1>Job Runner</h1>
    <div class=\"muted\">Queue and schedule overview with latest agent answers. Auto-refreshes every 5s.</div>

    <div class=\"stats\">
        <div class=\"card\"><div class=\"label\">Total</div><div class=\"value\">{len(jobs)}</div></div>
        <div class=\"card\"><div class=\"label\">Queued</div><div class=\"value\">{queued}</div></div>
        <div class=\"card\"><div class=\"label\">Scheduled</div><div class=\"value\">{scheduled}</div></div>
        <div class=\"card\"><div class=\"label\">Waiting Event</div><div class=\"value\">{waiting_event}</div></div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>ID</th>
                <th>Status</th>
                <th>Trigger</th>
                <th>Next Run</th>
                <th>Last Run</th>
                <th>Last Error</th>
                <th>Last Answer</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>

    <script>setTimeout(() => window.location.reload(), 5000);</script>
</body>
</html>
"""
        return HTMLResponse(content=html)


@app.post("/jobs")
async def create_job(payload: CreateJobRequest, request: Request):
    _verify_internal_api_key(request)
    service: JobService = app.state.service
    try:
        job = await service.create_job(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return job.model_dump()


@app.get("/jobs")
async def list_jobs(request: Request, thread_id: str | None = Query(default=None)):
    _verify_internal_api_key(request)
    service: JobService = app.state.service
    jobs = await service.list_jobs(thread_id=thread_id)
    return {"jobs": [job.model_dump() for job in jobs]}


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str, request: Request):
    _verify_internal_api_key(request)
    service: JobService = app.state.service
    try:
        job = await service.delete_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": job.model_dump()}


@app.post("/jobs/{job_id}/run")
async def run_job(job_id: str, request: Request):
    _verify_internal_api_key(request)
    service: JobService = app.state.service
    try:
        result = await service.run_job_now(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    return result
