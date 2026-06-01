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
from copilot.jobs.store import JobRunNotCancellable, JobStore, utc_now
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

        run = await self.repo.try_start_job_run(
            job_id=job.id,
            source=JobRunSource.TIME,
            trigger_payload={"source": "time"},
            now=now + timedelta(seconds=1),
        )
        self.assertIsNotNone(run)
        await self.repo.finish_job_run(
            run_id=run.id,
            job_id=job.id,
            now=now + timedelta(seconds=1),
            status=JobRunStatus.SUCCEEDED,
            error=None,
            response_text="all good",
            result={"ok": True, "assistant": "all good", "observed_value": 42},
            next_run_at=now + timedelta(seconds=61),
        )

        updated = await self.repo.get_job(job.id)
        self.assertEqual(updated.run_count, 1)
        self.assertEqual(updated.last_response, "all good")
        self.assertEqual(updated.next_run_at, now + timedelta(seconds=61))
        runs = await self.repo.list_job_runs(job.id)
        self.assertEqual([job_run.id for job_run in runs], [run.id])
        self.assertEqual(runs[0].status, JobRunStatus.SUCCEEDED)
        self.assertEqual(runs[0].result["observed_value"], 42)

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

        run = await self.repo.try_start_job_run(
            job_id=job.id,
            source=JobRunSource.EVENT,
            trigger_payload={"source": "event"},
            now=utc_now(),
        )
        self.assertIsNotNone(run)
        await self.repo.finish_job_run(
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

    async def test_duplicate_active_run_is_recorded_as_skipped_without_replacing_active_job(self):
        now = utc_now()
        job = await self.repo.create_job(
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

        active = await self.repo.try_start_job_run(
            job_id=job.id,
            source=JobRunSource.MANUAL,
            trigger_payload={"source": "manual"},
            now=now,
        )
        skipped = await self.repo.try_start_job_run(
            job_id=job.id,
            source=JobRunSource.TIME,
            trigger_payload={"source": "time"},
            now=now + timedelta(seconds=1),
        )

        self.assertIsNotNone(active)
        self.assertIsNotNone(skipped)
        self.assertEqual(skipped.status, JobRunStatus.SKIPPED)
        updated = await self.repo.get_job(job.id)
        self.assertEqual(updated.active_run_id, active.id)
        self.assertEqual(updated.last_run_status, JobRunStatus.RUNNING)
        self.assertEqual(updated.run_count, 1)

    async def test_waiting_run_keeps_active_lease_until_reply_finishes(self):
        now = utc_now()
        job = await self.repo.create_job(
            CreateJobRequest(
                name="human check",
                created_from_thread_id="thread-1",
                prompt="ask if needed",
                trigger_kind=JobTriggerKind.TIME,
                schedule_kind=TimeTriggerKind.INTERVAL,
                interval_seconds=60,
            ),
            next_run_at=now,
            subscription_id=None,
        )
        run = await self.repo.try_start_job_run(
            job_id=job.id,
            source=JobRunSource.MANUAL,
            trigger_payload={"source": "manual"},
            now=now,
        )
        self.assertIsNotNone(run)

        await self.repo.finish_job_run(
            run_id=run.id,
            job_id=job.id,
            now=now + timedelta(seconds=1),
            status=JobRunStatus.WAITING_FOR_INPUT,
            error=None,
            response_text="Which temperature?",
            result={"ok": True, "status": "waiting_for_input"},
            waiting_question="Which temperature?",
        )
        waiting = await self.repo.get_job(job.id)
        self.assertEqual(waiting.active_run_id, run.id)
        self.assertEqual(waiting.waiting_question, "Which temperature?")

        reply_run = await self.repo.start_reply_job_run(
            job_id=job.id,
            message="21 C",
            previous_run_id=run.id,
            now=now + timedelta(seconds=2),
        )
        self.assertEqual(reply_run.job_thread_id, job.job_thread_id)
        await self.repo.finish_job_run(
            run_id=reply_run.id,
            job_id=job.id,
            now=now + timedelta(seconds=3),
            status=JobRunStatus.SUCCEEDED,
            error=None,
            response_text="done",
            result={"ok": True},
        )
        finished = await self.repo.get_job(job.id)
        self.assertIsNone(finished.active_run_id)
        self.assertIsNone(finished.waiting_question)

    async def test_stale_running_runs_are_marked_failed(self):
        now = utc_now()
        job = await self.repo.create_job(
            CreateJobRequest(
                name="stale check",
                created_from_thread_id="thread-1",
                prompt="check",
                trigger_kind=JobTriggerKind.TIME,
                schedule_kind=TimeTriggerKind.INTERVAL,
                interval_seconds=60,
            ),
            next_run_at=now,
            subscription_id=None,
        )
        run = await self.repo.try_start_job_run(
            job_id=job.id,
            source=JobRunSource.MANUAL,
            trigger_payload={"source": "manual"},
            now=now,
        )
        self.assertIsNotNone(run)

        count = await self.repo.mark_stale_running_runs_failed(
            cutoff=now + timedelta(seconds=1),
            now=now + timedelta(seconds=2),
        )

        self.assertEqual(count, 1)
        updated = await self.repo.get_job(job.id)
        self.assertEqual(updated.last_run_status, JobRunStatus.FAILED)
        self.assertEqual(updated.run_count, 1)
        self.assertIsNone(updated.active_run_id)

    async def test_update_job_changes_payload_and_reschedules_interval(self):
        now = utc_now()
        job = await self.repo.create_job(
            CreateJobRequest(
                name="energy summary",
                created_from_thread_id="thread-1",
                prompt="summarize energy",
                trigger_kind=JobTriggerKind.TIME,
                schedule_kind=TimeTriggerKind.INTERVAL,
                interval_seconds=60,
            ),
            next_run_at=now,
            subscription_id=None,
        )

        updated = await self.repo.update_job(
            job.id,
            name="renamed",
            prompt="summarize energy and water",
            interval_seconds=120,
        )
        self.assertEqual(updated.name, "renamed")
        self.assertEqual(updated.prompt, "summarize energy and water")
        self.assertEqual(updated.interval_seconds, 120)
        self.assertIsNotNone(updated.next_run_at)

        # Disabling clears the next run; re-enabling recomputes it.
        disabled = await self.repo.update_job(job.id, enabled=False)
        self.assertFalse(disabled.enabled)
        self.assertIsNone(disabled.next_run_at)

        reenabled = await self.repo.update_job(job.id, enabled=True)
        self.assertTrue(reenabled.enabled)
        self.assertIsNotNone(reenabled.next_run_at)

    async def test_cancel_active_run_releases_lease(self):
        now = utc_now()
        job = await self.repo.create_job(
            CreateJobRequest(
                name="cancellable",
                created_from_thread_id="thread-1",
                prompt="long running",
                trigger_kind=JobTriggerKind.TIME,
                schedule_kind=TimeTriggerKind.INTERVAL,
                interval_seconds=60,
            ),
            next_run_at=now,
            subscription_id=None,
        )

        with self.assertRaises(JobRunNotCancellable):
            await self.repo.cancel_active_run(job.id)

        run = await self.repo.try_start_job_run(
            job_id=job.id,
            source=JobRunSource.MANUAL,
            trigger_payload={"source": "manual"},
            now=now,
        )
        self.assertIsNotNone(run)

        cancelled = await self.repo.cancel_active_run(job.id)
        self.assertEqual(cancelled.last_run_status, JobRunStatus.CANCELLED)
        self.assertIsNone(cancelled.active_run_id)

        runs = await self.repo.list_job_runs(job.id)
        self.assertEqual(runs[0].status, JobRunStatus.CANCELLED)
        self.assertIsNotNone(runs[0].finished_at)


if __name__ == "__main__":
    unittest.main()
