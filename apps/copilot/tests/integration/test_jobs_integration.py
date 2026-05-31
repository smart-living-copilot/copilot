from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest
import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from copilot.core.settings import Settings
from copilot.jobs.models import (
    CreateJobRequest,
    JobRunSource,
    JobRunStatus,
    JobTriggerKind,
    TimeTriggerKind,
)
from copilot.jobs.results import JobRunEventPublisher
from copilot.jobs.routes import router as jobs_router
from copilot.jobs.schedule import build_schedule_source, schedule_id_for_job
from copilot.jobs.service import JobService
from copilot.jobs.store import JobStore, utc_now
from copilot.threads.store import get_thread, list_threads

pytestmark = pytest.mark.integration


def _run(coro):
    return asyncio.run(coro)


def _get_schedules(settings: Settings):
    return _run(build_schedule_source(settings).get_schedules())


def _build_jobs_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.state.service = JobService(settings)
    app.include_router(jobs_router)
    return app


def test_jobs_api_persists_time_job_and_syncs_redis_schedule(
    jobs_integration_environment,
) -> None:
    settings = Settings(
        redis_url=jobs_integration_environment.redis_url,
        internal_api_key="",
    )
    app = _build_jobs_app(settings)

    with TestClient(app) as client:
        create_response = client.post(
            "/jobs",
            json={
                "name": "check doors",
                "created_from_thread_id": "thread-1",
                "prompt": "Check all exterior doors",
                "trigger_kind": "time",
                "schedule_kind": "interval",
                "interval_seconds": 60,
            },
        )

        assert create_response.status_code == 200
        created = create_response.json()
        assert created["name"] == "check doors"
        assert created["created_from_thread_id"] == "thread-1"
        assert created["job_thread_id"] == f"job:{created['id']}"
        assert created["trigger_kind"] == "time"
        assert created["action_kind"] == "prompt"
        assert created["enabled"] is True
        assert created["next_run_at"] is not None
        assert [thread["id"] for thread in list_threads()] == []
        hidden_thread = get_thread(created["job_thread_id"])
        assert hidden_thread is not None
        assert hidden_thread["kind"] == "job"
        assert hidden_thread["visible"] is False
        assert hidden_thread["jobId"] == created["id"]

        list_response = client.get("/jobs", params={"created_from_thread_id": "thread-1"})
        assert list_response.status_code == 200
        assert [job["id"] for job in list_response.json()["jobs"]] == [created["id"]]

        schedules = _get_schedules(settings)
        assert [schedule.schedule_id for schedule in schedules] == [
            schedule_id_for_job(created["id"])
        ]
        assert schedules[0].interval == 60

        delete_response = client.delete(f"/jobs/{created['id']}")
        assert delete_response.status_code == 200

        schedules = _get_schedules(settings)
        assert schedules == []

        get_response = client.get(f"/jobs/{created['id']}")
        assert get_response.status_code == 404


def test_job_run_event_publisher_writes_current_job_snapshot_to_redis_stream(
    jobs_integration_environment,
) -> None:
    settings = Settings(redis_url=jobs_integration_environment.redis_url)
    repo = JobStore()
    now = utc_now()
    job = _run(
        repo.create_job(
            CreateJobRequest(
                name="daily check",
                created_from_thread_id="thread-2",
                prompt="summarize system status",
                trigger_kind=JobTriggerKind.TIME,
                schedule_kind=TimeTriggerKind.INTERVAL,
                interval_seconds=300,
            ),
            next_run_at=now,
            subscription_id=None,
        )
    )
    run = _run(
        repo.try_start_job_run(
            job_id=job.id,
            source=JobRunSource.TIME,
            trigger_payload={"source": "time"},
            now=now + timedelta(seconds=1),
        )
    )
    assert run is not None
    _run(
        repo.finish_job_run(
            run_id=run.id,
            job_id=job.id,
            now=now + timedelta(seconds=1),
            status=JobRunStatus.SUCCEEDED,
            error=None,
            response_text="all clear",
            result={"ok": True, "assistant": "all clear"},
            next_run_at=now + timedelta(seconds=301),
        )
    )
    runs = _run(repo.list_job_runs(job.id))
    assert [job_run.id for job_run in runs] == [run.id]

    event_id = _run(
        JobRunEventPublisher(settings, repo=repo).publish_job_run(job.id, run_id=run.id)
    )

    assert event_id is not None
    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        records = redis_client.xrange(settings.jobs_run_events_stream)
    finally:
        redis_client.close()

    assert len(records) == 1
    payload = json.loads(records[0][1]["payload"])
    assert payload["type"] == "job_run"
    assert payload["job"]["id"] == job.id
    assert payload["job"]["last_response"] == "all clear"
    assert payload["job"]["run_count"] == 1
    assert payload["run"]["id"] == run.id
    assert payload["run"]["status"] == "succeeded"
