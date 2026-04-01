"""LangChain tools for managing automation jobs in the standalone job-runner service."""

from __future__ import annotations

from typing import Any

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from copilot.models import Settings

_settings = Settings()


def _headers() -> dict[str, str]:
    if _settings.internal_api_key:
        return {"Authorization": f"Bearer {_settings.internal_api_key}"}
    return {}


@tool
async def create_job(
    name: str,
    prompt: str,
    trigger_type: str,
    config: RunnableConfig,
    thread_id: str | None = None,
    run_at: str | None = None,
    interval_seconds: int | None = None,
    thing_id: str | None = None,
    event_name: str | None = None,
    subscription_input: Any = None,
) -> dict[str, Any]:
    """Create an automation job.

    trigger_type:
    - "time": use run_at (ISO datetime) or interval_seconds
    - "event": use thing_id and event_name
    """
    payload = {
        "name": name,
        "thread_id": thread_id
        or config.get("configurable", {}).get("thread_id", "default"),
        "prompt": prompt,
        "trigger_type": trigger_type,
        "run_at": run_at,
        "interval_seconds": interval_seconds,
        "thing_id": thing_id,
        "event_name": event_name,
        "subscription_input": subscription_input,
    }
    try:
        async with httpx.AsyncClient(timeout=float(_settings.job_runner_timeout_seconds)) as client:
            response = await client.post(
                f"{_settings.job_runner_url}/jobs",
                json=payload,
                headers=_headers(),
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        return {"error": "Job runner service is unavailable."}
    except httpx.HTTPStatusError as exc:
        detail = None
        try:
            detail = exc.response.json().get("detail")
        except Exception:
            detail = None
        return {"error": detail or f"Job creation failed with status {exc.response.status_code}."}


@tool
async def list_jobs(config: RunnableConfig, thread_id: str | None = None) -> dict[str, Any]:
    """List automation jobs, optionally filtered by thread_id.

    If thread_id is omitted, uses the current conversation thread id.
    """
    scoped_thread_id = thread_id or config.get("configurable", {}).get("thread_id")
    params = {"thread_id": scoped_thread_id} if scoped_thread_id else None
    try:
        async with httpx.AsyncClient(timeout=float(_settings.job_runner_timeout_seconds)) as client:
            response = await client.get(
                f"{_settings.job_runner_url}/jobs",
                params=params,
                headers=_headers(),
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        return {"error": "Job runner service is unavailable."}
    except httpx.HTTPStatusError as exc:
        return {"error": f"Listing jobs failed with status {exc.response.status_code}."}


@tool
async def delete_job(job_id: str) -> dict[str, Any]:
    """Delete an automation job by id."""
    try:
        async with httpx.AsyncClient(timeout=float(_settings.job_runner_timeout_seconds)) as client:
            response = await client.delete(
                f"{_settings.job_runner_url}/jobs/{job_id}",
                headers=_headers(),
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        return {"error": "Job runner service is unavailable."}
    except httpx.HTTPStatusError as exc:
        return {"error": f"Deleting job failed with status {exc.response.status_code}."}