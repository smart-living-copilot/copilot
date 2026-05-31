import os
import unittest
from datetime import timedelta

import pytest

from copilot.core.config import get_settings
from copilot.core.database import (
    get_connection_pool,
    get_session_factory,
    get_sqlalchemy_engine,
    init_db,
)
from copilot.jobs.models import (
    CreateJobRequest,
    JobActionKind,
    JobRunSource,
    JobRunStatus,
    JobTriggerKind,
    TimeTriggerKind,
)
from copilot.jobs.store import JobStore, utc_now
from copilot.threads.store import init_thread_store

pytestmark = pytest.mark.skipif(
    not os.getenv("COPILOT_TEST_DATABASE_URL"),
    reason="COPILOT_TEST_DATABASE_URL is required for Postgres job repository tests",
)


def _close_cached_pool() -> None:
    if get_connection_pool.cache_info().currsize:
        get_connection_pool().close()
    get_connection_pool.cache_clear()
    get_session_factory.cache_clear()
    if get_sqlalchemy_engine.cache_info().currsize:
        get_sqlalchemy_engine().dispose()
    get_sqlalchemy_engine.cache_clear()


class JobStoreTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ["REGISTRY_DATABASE_URL"] = os.environ["COPILOT_TEST_DATABASE_URL"]
        get_settings.cache_clear()
        _close_cached_pool()
        init_db()
        init_thread_store()
        with get_connection_pool().connection() as connection:
            connection.execute("TRUNCATE job_runs, jobs, threads RESTART IDENTITY CASCADE")
            connection.commit()
        self.repo = JobStore()

    async def asyncTearDown(self):
        get_settings.cache_clear()
        _close_cached_pool()

    async def test_time_job_lifecycle(self):
        now = utc_now()
        job = await self.repo.create_job(
            CreateJobRequest(
                name="daily check",
                created_from_thread_id="thread-1",
                prompt="check the system",
                trigger_kind=JobTriggerKind.TIME,
                schedule_kind=TimeTriggerKind.INTERVAL,
                interval_seconds=60,
            ),
            next_run_at=now,
            subscription_id=None,
        )

        enabled = await self.repo.list_enabled_time_jobs()
        self.assertEqual([enabled_job.id for enabled_job in enabled], [job.id])

        run = await self.repo.create_job_run(
            job=job,
            source=JobRunSource.TIME,
            trigger_payload={"source": "time"},
            now=now + timedelta(seconds=1),
        )
        await self.repo.record_job_result(
            run_id=run.id,
            job_id=job.id,
            now=now + timedelta(seconds=1),
            status=JobRunStatus.SUCCEEDED,
            error=None,
            response_text="all good",
            result={"ok": True, "assistant": "all good"},
            last_fetch_value="42",
            next_run_at=now + timedelta(seconds=61),
        )

        updated = await self.repo.get_job(job.id)
        self.assertEqual(updated.run_count, 1)
        self.assertEqual(updated.last_response, "all good")
        self.assertEqual(updated.last_fetch_value, "42")
        self.assertEqual(updated.next_run_at, now + timedelta(seconds=61))
        runs = await self.repo.list_job_runs(job.id)
        self.assertEqual([job_run.id for job_run in runs], [run.id])
        self.assertEqual(runs[0].status, JobRunStatus.SUCCEEDED)

    async def test_event_job_subscription_lifecycle(self):
        job = await self.repo.create_job(
            CreateJobRequest(
                name="event check",
                created_from_thread_id="thread-2",
                action_kind=JobActionKind.ANALYSIS,
                analysis_code="print('ok')",
                trigger_kind=JobTriggerKind.EVENT,
                thing_id="thing-1",
                event_name="changed",
                subscription_input={"threshold": 3},
            ),
            next_run_at=None,
            subscription_id="sub-1",
        )

        jobs = await self.repo.list_event_jobs_for_subscription("sub-1")
        self.assertEqual([event_job.id for event_job in jobs], [job.id])
        self.assertEqual(jobs[0].subscription_input, {"threshold": 3})

        await self.repo.set_subscription_id(job.id, "sub-2")
        self.assertEqual(await self.repo.list_event_jobs_for_subscription("sub-1"), [])
        self.assertEqual(
            [event_job.id for event_job in await self.repo.list_enabled_event_jobs()],
            [job.id],
        )

        run = await self.repo.create_job_run(
            job=job,
            source=JobRunSource.EVENT,
            trigger_payload={"source": "event"},
            now=utc_now(),
        )
        await self.repo.record_job_result(
            run_id=run.id,
            job_id=job.id,
            now=utc_now(),
            status=JobRunStatus.FAILED,
            error="boom",
            response_text=None,
            result={"ok": False, "error": "boom"},
        )
        updated = await self.repo.get_job(job.id)
        self.assertEqual(updated.run_count, 1)
        self.assertEqual(updated.last_error, "boom")

        deleted = await self.repo.delete_job(job.id)
        self.assertEqual(deleted.id, job.id)
        with self.assertRaises(KeyError):
            await self.repo.get_job(job.id)

    async def test_list_enabled_time_jobs_excludes_disabled(self):
        now = utc_now()
        recurring = await self.repo.create_job(
            CreateJobRequest(
                name="recurring check",
                created_from_thread_id="thread-1",
                prompt="check the system",
                trigger_kind=JobTriggerKind.TIME,
                schedule_kind=TimeTriggerKind.INTERVAL,
                interval_seconds=60,
            ),
            next_run_at=now,
            subscription_id=None,
        )
        one_shot = await self.repo.create_job(
            CreateJobRequest(
                name="one shot",
                created_from_thread_id="thread-1",
                prompt="check once",
                trigger_kind=JobTriggerKind.TIME,
                schedule_kind=TimeTriggerKind.ONCE,
                run_at=now,
            ),
            next_run_at=now,
            subscription_id=None,
        )

        enabled_ids = {job.id for job in await self.repo.list_enabled_time_jobs()}
        self.assertEqual(enabled_ids, {recurring.id, one_shot.id})

        await self.repo.disable_job(one_shot.id)

        enabled_ids = {job.id for job in await self.repo.list_enabled_time_jobs()}
        self.assertEqual(enabled_ids, {recurring.id})

        disabled = await self.repo.get_job(one_shot.id)
        self.assertFalse(disabled.enabled)
        self.assertIsNone(disabled.next_run_at)


if __name__ == "__main__":
    unittest.main()
