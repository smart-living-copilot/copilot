import unittest
from datetime import datetime, timezone

from copilot.agent.tools import job_scheduler
from copilot.jobs.models import (
    CreateJobRequest,
    Job,
    JobActionKind,
    JobOutputKind,
    JobTriggerKind,
    TimeTriggerKind,
)
from copilot.jobs.active import set_active_job_service


def _job(**overrides) -> Job:
    now = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
    values = {
        "id": "job-123",
        "name": "demo",
        "created_from_thread_id": "thread-1",
        "job_thread_id": "job:job-123",
        "action_kind": JobActionKind.PROMPT,
        "prompt": "check",
        "analysis_code": None,
        "enabled": True,
        "trigger_kind": JobTriggerKind.TIME,
        "schedule_kind": TimeTriggerKind.INTERVAL,
        "run_at": None,
        "interval_seconds": 10,
        "next_run_at": now,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return Job(**values)


class _FakeService:
    def __init__(self, *, run_result=None, create_error=None) -> None:
        self._run_result = run_result or {"ok": True, "response": "done"}
        self._create_error = create_error
        self.created_requests: list[CreateJobRequest] = []
        self.deleted: list[str] = []
        self.ran: list[str] = []
        self.listed: list[str | None] = []

    async def create_job(self, request: CreateJobRequest) -> Job:
        if self._create_error is not None:
            raise self._create_error
        self.created_requests.append(request)
        return _job(
            name=request.name,
            created_from_thread_id=request.created_from_thread_id,
            action_kind=request.action_kind,
            interaction_mode=request.interaction_mode,
            output_kind=request.output_kind,
            prompt=request.prompt,
            analysis_code=request.analysis_code,
            record_schema=request.record_schema,
            record_schema_version=request.record_schema_version,
            virtual_thing_id=request.virtual_thing_id,
            trigger_kind=request.trigger_kind,
            schedule_kind=request.schedule_kind,
            run_at=request.run_at,
            interval_seconds=request.interval_seconds,
            cron_expression=request.cron_expression,
            cron_timezone=request.cron_timezone,
        )

    async def run_job_now(self, job_id: str) -> dict:
        self.ran.append(job_id)
        return self._run_result

    async def delete_job(self, job_id: str) -> Job:
        self.deleted.append(job_id)
        return _job(id=job_id)

    async def list_jobs(self, created_from_thread_id: str | None = None) -> list[Job]:
        self.listed.append(created_from_thread_id)
        return [_job()]


class JobSchedulerTestCase(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        set_active_job_service(None)

    async def test_prompt_job_tools_expose_runtime_instructions_argument(self) -> None:
        self.assertIn("run_instructions", job_scheduler.create_prompt_job.args)
        self.assertNotIn("prompt", job_scheduler.create_prompt_job.args)
        self.assertIn("run_instructions", job_scheduler.create_record_prompt_job.args)
        self.assertNotIn("prompt", job_scheduler.create_record_prompt_job.args)

    async def test_create_analysis_job_returns_created_job_without_running(self) -> None:
        service = _FakeService(run_result={"ok": False, "error": "boom"})
        set_active_job_service(service)

        result = await job_scheduler.create_analysis_job.ainvoke(
            {
                "name": "demo job",
                "analysis_code": "print('hello')",
                "trigger_kind": "time",
                "schedule_kind": "interval",
                "interval_seconds": 60,
            },
            config={"configurable": {"thread_id": "thread-1"}},
        )

        self.assertEqual(result["id"], "job-123")
        self.assertNotIn("test_run", result)
        self.assertEqual(service.ran, [])
        self.assertEqual(service.deleted, [])
        self.assertEqual(service.created_requests[0].action_kind, JobActionKind.ANALYSIS)

    async def test_create_prompt_job_returns_created_job_without_running(self) -> None:
        service = _FakeService(run_result={"ok": True, "response": "ran"})
        set_active_job_service(service)

        result = await job_scheduler.create_prompt_job.ainvoke(
            {
                "name": "demo job",
                "run_instructions": "check the house",
                "trigger_kind": "time",
                "schedule_kind": "interval",
                "interval_seconds": 10,
            },
            config={"configurable": {"thread_id": "thread-1"}},
        )

        self.assertEqual(result["id"], "job-123")
        self.assertNotIn("test_run", result)
        self.assertEqual(service.created_requests[0].created_from_thread_id, "thread-1")
        self.assertEqual(service.created_requests[0].interval_seconds, 10)
        self.assertEqual(service.ran, [])
        self.assertEqual(service.deleted, [])

    async def test_create_prompt_job_passes_cron_schedule(self) -> None:
        service = _FakeService()
        set_active_job_service(service)

        result = await job_scheduler.create_prompt_job.ainvoke(
            {
                "name": "weekly check",
                "run_instructions": "Check the house.",
                "trigger_kind": "time",
                "schedule_kind": "cron",
                "cron_expression": "0 9 * * sun",
                "cron_timezone": "Europe/Berlin",
            },
            config={"configurable": {"thread_id": "thread-1"}},
        )

        self.assertEqual(result["schedule_kind"], "cron")
        request = service.created_requests[0]
        self.assertEqual(request.schedule_kind, TimeTriggerKind.CRON)
        self.assertEqual(request.cron_expression, "0 9 * * sun")
        self.assertEqual(request.cron_timezone, "Europe/Berlin")

    async def test_create_record_prompt_job_passes_schema_contract(self) -> None:
        service = _FakeService()
        set_active_job_service(service)

        result = await job_scheduler.create_record_prompt_job.ainvoke(
            {
                "name": "morning check-in",
                "run_instructions": "Ask how I feel and store mood.",
                "record_schema": {
                    "type": "object",
                    "properties": {"mood": {"type": "string"}},
                    "required": ["mood"],
                },
                "trigger_kind": "time",
                "schedule_kind": "interval",
                "interval_seconds": 86400,
                "virtual_thing_title": "Morning Check-ins",
            },
            config={"configurable": {"thread_id": "thread-1"}},
        )

        self.assertEqual(result["output_kind"], "structured_record")
        request = service.created_requests[0]
        self.assertEqual(request.output_kind, JobOutputKind.STRUCTURED_RECORD)
        self.assertEqual(request.record_schema["required"], ["mood"])
        self.assertEqual(request.virtual_thing_title, "Morning Check-ins")

    async def test_create_prompt_job_reports_validation_error(self) -> None:
        service = _FakeService(
            create_error=ValueError("time jobs require run_at or interval_seconds")
        )
        set_active_job_service(service)

        result = await job_scheduler.create_prompt_job.ainvoke(
            {
                "name": "demo job",
                "run_instructions": "check",
                "trigger_kind": "time",
            },
            config={"configurable": {"thread_id": "thread-1"}},
        )

        self.assertEqual(result, {"error": "time jobs require run_at or interval_seconds"})

    async def test_tools_report_when_service_unavailable(self) -> None:
        set_active_job_service(None)

        result = await job_scheduler.list_jobs.ainvoke({})

        self.assertEqual(result, {"error": "Job service is not ready"})

    async def test_list_delete_run_delegate_to_service(self) -> None:
        service = _FakeService(run_result={"ok": True})
        set_active_job_service(service)

        listed = await job_scheduler.list_jobs.ainvoke({"created_from_thread_id": "thread-1"})
        deleted = await job_scheduler.delete_job.ainvoke({"job_id": "job-9"})
        ran = await job_scheduler.run_job_now.ainvoke({"job_id": "job-9"})

        self.assertEqual(listed["jobs"][0]["id"], "job-123")
        self.assertEqual(service.listed, ["thread-1"])
        self.assertTrue(deleted["ok"])
        self.assertEqual(service.deleted, ["job-9"])
        self.assertEqual(ran, {"ok": True})
        self.assertEqual(service.ran, ["job-9"])


if __name__ == "__main__":
    unittest.main()
