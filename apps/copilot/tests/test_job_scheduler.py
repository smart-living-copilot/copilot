import unittest
from datetime import datetime, timezone

from copilot.agent.tools import job_scheduler
from copilot.jobs.models import CreateJobRequest, Job
from copilot.jobs.active import set_active_job_service


def _job(**overrides) -> Job:
    now = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
    values = {
        "id": "job-123",
        "name": "demo",
        "thread_id": "thread-1",
        "enabled": True,
        "trigger_type": "time",
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
        return _job(name=request.name, thread_id=request.thread_id)

    async def run_job_now(self, job_id: str) -> dict:
        self.ran.append(job_id)
        return self._run_result

    async def delete_job(self, job_id: str) -> Job:
        self.deleted.append(job_id)
        return _job(id=job_id)

    async def list_jobs(self, thread_id: str | None = None) -> list[Job]:
        self.listed.append(thread_id)
        return [_job()]


class JobSchedulerTestCase(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        set_active_job_service(None)

    async def test_create_analysis_job_returns_created_job_without_running(self) -> None:
        service = _FakeService(run_result={"ok": False, "error": "boom"})
        set_active_job_service(service)

        result = await job_scheduler.create_analysis_job.ainvoke(
            {
                "name": "demo job",
                "analysis_code": "print('hello')",
                "trigger_type": "time",
            },
            config={"configurable": {"thread_id": "thread-1"}},
        )

        self.assertEqual(result["id"], "job-123")
        self.assertNotIn("test_run", result)
        self.assertEqual(service.ran, [])
        self.assertEqual(service.deleted, [])
        self.assertEqual(service.created_requests[0].job_type, "analysis")

    async def test_create_job_returns_created_job_without_running(self) -> None:
        service = _FakeService(run_result={"ok": True, "response": "ran"})
        set_active_job_service(service)

        result = await job_scheduler.create_job.ainvoke(
            {
                "name": "demo job",
                "prompt": "check the house",
                "trigger_type": "time",
                "interval_seconds": 10,
            },
            config={"configurable": {"thread_id": "thread-1"}},
        )

        self.assertEqual(result["id"], "job-123")
        self.assertNotIn("test_run", result)
        self.assertEqual(service.created_requests[0].thread_id, "thread-1")
        self.assertEqual(service.created_requests[0].interval_seconds, 10)
        self.assertEqual(service.ran, [])
        self.assertEqual(service.deleted, [])

    async def test_create_job_reports_validation_error(self) -> None:
        service = _FakeService(create_error=ValueError("time jobs require run_at or interval_seconds"))
        set_active_job_service(service)

        result = await job_scheduler.create_job.ainvoke(
            {
                "name": "demo job",
                "prompt": "check",
                "trigger_type": "time",
            },
            config={"configurable": {"thread_id": "thread-1"}},
        )

        self.assertEqual(result, {"error": "time jobs require run_at or interval_seconds"})

    async def test_tools_report_when_service_unavailable(self) -> None:
        set_active_job_service(None)

        result = await job_scheduler.list_jobs.ainvoke({})

        self.assertEqual(result, {"error": "Job runner is not enabled"})

    async def test_list_delete_run_delegate_to_service(self) -> None:
        service = _FakeService(run_result={"ok": True})
        set_active_job_service(service)

        listed = await job_scheduler.list_jobs.ainvoke({"thread_id": "thread-1"})
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
