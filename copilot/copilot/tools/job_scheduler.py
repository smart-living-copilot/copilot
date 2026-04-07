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


def _thread_id_from_config(config: RunnableConfig, thread_id: str | None) -> str:
    return thread_id or config.get("configurable", {}).get("thread_id", "default")


def _response_error_detail(exc: httpx.HTTPStatusError, fallback: str) -> str:
    try:
        detail = exc.response.json().get("detail")
    except Exception:
        detail = None
    return detail or fallback


async def _delete_job_with_client(client: httpx.AsyncClient, job_id: str) -> dict[str, Any]:
    response = await client.delete(
        f"{_settings.job_runner_url}/jobs/{job_id}",
        headers=_headers(),
    )
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {"ok": True}


async def _validate_new_job(
    client: httpx.AsyncClient,
    created_job: dict[str, Any],
) -> dict[str, Any]:
    job_id = created_job.get("id")
    if not job_id:
        return created_job

    try:
        run_response = await client.post(
            f"{_settings.job_runner_url}/jobs/{job_id}/run",
            headers=_headers(),
        )
        run_response.raise_for_status()
        run_result = run_response.json()
    except httpx.ConnectError:
        run_result = {"ok": False, "error": "Job runner service is unavailable during validation."}
    except httpx.HTTPStatusError as exc:
        run_result = {
            "ok": False,
            "error": _response_error_detail(
                exc,
                f"Running job failed with status {exc.response.status_code}.",
            ),
        }

    if isinstance(run_result, dict) and run_result.get("ok"):
        created_job["test_run"] = run_result
        return created_job

    deleted_failed_job = False
    delete_error = None
    try:
        await _delete_job_with_client(client, str(job_id))
        deleted_failed_job = True
    except httpx.ConnectError:
        delete_error = "Job runner service is unavailable during cleanup."
    except httpx.HTTPStatusError as exc:
        delete_error = _response_error_detail(
            exc,
            f"Deleting failed job failed with status {exc.response.status_code}.",
        )

    error_message = "Newly created job failed validation and was deleted."
    if isinstance(run_result, dict) and run_result.get("error"):
        error_message = f"{error_message} Validation error: {run_result['error']}"
    if delete_error:
        error_message = f"{error_message} Cleanup error: {delete_error}"

    return {
        "error": error_message,
        "job": created_job,
        "test_run": run_result,
        "deleted_failed_job": deleted_failed_job,
    }


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
        "thread_id": _thread_id_from_config(config, thread_id),
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
            created_job = response.json()
            if not isinstance(created_job, dict):
                return {"error": "Job creation returned an invalid response."}
            return await _validate_new_job(client, created_job)
    except httpx.ConnectError:
        return {"error": "Job runner service is unavailable."}
    except httpx.HTTPStatusError as exc:
        return {
            "error": _response_error_detail(
                exc,
                f"Job creation failed with status {exc.response.status_code}.",
            )
        }


@tool
async def create_analysis_job(
    name: str,
    analysis_code: str,
    config: RunnableConfig,
    thread_id: str | None = None,
    run_at: str | None = None,
    interval_seconds: int | None = None,
) -> dict[str, Any]:
    """Create a periodic analysis job.

    Analysis jobs run Python in the code-executor sandbox on a schedule.
    They currently support only time-based triggers, so provide either:
    - run_at: one-time ISO datetime, or
    - interval_seconds: recurring cadence in seconds.
    """
    payload = {
        "name": name,
        "thread_id": _thread_id_from_config(config, thread_id),
        "job_type": "analysis",
        "trigger_type": "time",
        "analysis_code": analysis_code,
        "run_at": run_at,
        "interval_seconds": interval_seconds,
    }
    try:
        async with httpx.AsyncClient(timeout=float(_settings.job_runner_timeout_seconds)) as client:
            response = await client.post(
                f"{_settings.job_runner_url}/jobs",
                json=payload,
                headers=_headers(),
            )
            response.raise_for_status()
            created_job = response.json()
            if not isinstance(created_job, dict):
                return {"error": "Analysis job creation returned an invalid response."}
            return await _validate_new_job(client, created_job)
    except httpx.ConnectError:
        return {"error": "Job runner service is unavailable."}
    except httpx.HTTPStatusError as exc:
        return {
            "error": _response_error_detail(
                exc,
                f"Analysis job creation failed with status {exc.response.status_code}.",
            )
        }


@tool
async def list_jobs(config: RunnableConfig, thread_id: str | None = None) -> dict[str, Any]:
    """List automation jobs, optionally filtered by thread_id.

    If thread_id is omitted, returns all jobs.
    """
    params = {"thread_id": thread_id} if thread_id else None
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
            return await _delete_job_with_client(client, job_id)
    except httpx.ConnectError:
        return {"error": "Job runner service is unavailable."}
    except httpx.HTTPStatusError as exc:
        return {
            "error": _response_error_detail(
                exc,
                f"Deleting job failed with status {exc.response.status_code}.",
            )
        }


@tool
async def run_job_now(job_id: str) -> dict[str, Any]:
    """Trigger an automation job immediately and return the execution result."""
    try:
        async with httpx.AsyncClient(timeout=float(_settings.job_runner_timeout_seconds)) as client:
            response = await client.post(
                f"{_settings.job_runner_url}/jobs/{job_id}/run",
                headers=_headers(),
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        return {"error": "Job runner service is unavailable."}
    except httpx.HTTPStatusError as exc:
        return {
            "error": _response_error_detail(
                exc,
                f"Running job failed with status {exc.response.status_code}.",
            )
        }