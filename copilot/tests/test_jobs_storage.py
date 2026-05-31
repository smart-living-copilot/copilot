import os
import unittest
from datetime import timedelta

import pytest

from copilot.core.config import get_settings
from copilot.core.database import get_connection_pool, init_db
from copilot.jobs.models import CreateJobRequest
from copilot.jobs.store import JobStore, utc_now

pytestmark = pytest.mark.skipif(
    not os.getenv("COPILOT_TEST_DATABASE_URL"),
    reason="COPILOT_TEST_DATABASE_URL is required for Postgres job repository tests",
)


def _close_cached_pool() -> None:
    if get_connection_pool.cache_info().currsize:
        get_connection_pool().close()
    get_connection_pool.cache_clear()


class JobStoreTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ["REGISTRY_DATABASE_URL"] = os.environ["COPILOT_TEST_DATABASE_URL"]
        get_settings.cache_clear()
        _close_cached_pool()
        init_db()
        with get_connection_pool().connection() as connection:
            connection.execute("TRUNCATE jobs")
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
                thread_id="thread-1",
                prompt="check the system",
                trigger_type="time",
                interval_seconds=60,
            ),
            next_run_at=now,
            subscription_id=None,
        )

        enabled = await self.repo.list_enabled_time_jobs()
        self.assertEqual([enabled_job.id for enabled_job in enabled], [job.id])

        await self.repo.record_job_result(
            job_id=job.id,
            now=now + timedelta(seconds=1),
            success=True,
            error=None,
            response_text="all good",
            last_fetch_value="42",
        )

        updated = await self.repo.get_job(job.id)
        self.assertEqual(updated.run_count, 1)
        self.assertEqual(updated.last_response, "all good")
        self.assertEqual(updated.last_fetch_value, "42")

    async def test_event_job_subscription_lifecycle(self):
        job = await self.repo.create_job(
            CreateJobRequest(
                name="event check",
                thread_id="thread-2",
                job_type="analysis",
                analysis_code="print('ok')",
                trigger_type="event",
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

        await self.repo.record_job_result(
            job_id=job.id,
            now=utc_now(),
            success=False,
            error="boom",
            response_text=None,
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
                thread_id="thread-1",
                prompt="check the system",
                trigger_type="time",
                interval_seconds=60,
            ),
            next_run_at=now,
            subscription_id=None,
        )
        one_shot = await self.repo.create_job(
            CreateJobRequest(
                name="one shot",
                thread_id="thread-1",
                prompt="check once",
                trigger_type="time",
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
