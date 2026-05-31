from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from taskiq import ScheduledTask
from taskiq.exceptions import TaskiqResultTimeoutError

from copilot.core.settings import Settings
from copilot.jobs.events import JobEventConsumer
from copilot.jobs.executor import BackgroundAgentRunner, JobExecutor
from copilot.jobs.models import (
    CreateJobRequest,
    Job,
    JobActionKind,
    JobRun,
    JobRunSource,
    JobRunStatus,
    JobTriggerKind,
    TimeTriggerKind,
)
from copilot.jobs.routes import router as jobs_router
from copilot.jobs.schedule import (
    JobScheduleManager,
    schedule_id_for_job,
    scheduled_task_for_job,
)
from copilot.jobs.service import JobService


def _job(**overrides) -> Job:
    now = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
    values = {
        "id": "job-1",
        "name": "Demo job",
        "created_from_thread_id": "thread-1",
        "job_thread_id": "job:job-1",
        "action_kind": JobActionKind.PROMPT,
        "prompt": "Check the house",
        "analysis_code": None,
        "enabled": True,
        "trigger_kind": JobTriggerKind.TIME,
        "schedule_kind": TimeTriggerKind.INTERVAL,
        "run_at": None,
        "interval_seconds": 60,
        "next_run_at": now,
        "thing_id": None,
        "event_name": None,
        "subscription_id": None,
        "subscription_input": None,
        "created_at": now,
        "updated_at": now,
        "last_run_id": None,
        "last_run_at": None,
        "last_run_status": None,
        "last_error": None,
        "last_response": None,
        "run_count": 0,
        "last_fetch_value": None,
    }
    values.update(overrides)
    return Job(**values)


class _FakeGraph:
    def __init__(self) -> None:
        self.configs = []
        self.invocations = []

    def with_config(self, **config):
        self.configs.append(config)
        return self

    async def ainvoke(self, input_data, config):
        self.invocations.append((input_data, config))
        return {"messages": [AIMessage(content="background result")]}


class _FakeSaverContext:
    def __init__(self, saver) -> None:
        self.saver = saver
        self.closed = False

    async def __aenter__(self):
        return self.saver

    async def __aexit__(self, *_args):
        self.closed = True


class BackgroundAgentRunnerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_uses_postgres_checkpointer_and_hidden_job_thread_without_job_tools(
        self,
    ) -> None:
        graph = _FakeGraph()
        runner = BackgroundAgentRunner(Settings(openai_api_key="test"))
        saver = SimpleNamespace(setup=AsyncMock())
        saver_context = _FakeSaverContext(saver)
        conninfo_values = []

        class FakeAsyncPostgresSaver:
            @staticmethod
            def from_conn_string(conninfo):
                conninfo_values.append(conninfo)
                return saver_context

        with (
            patch("copilot.jobs.executor.init_db"),
            patch(
                "copilot.jobs.executor.get_registry_settings",
                return_value=SimpleNamespace(DATABASE_URL="postgresql://test/db"),
            ),
            patch("copilot.jobs.executor.psycopg_conninfo", return_value="conninfo"),
            patch("copilot.jobs.executor.AsyncPostgresSaver", FakeAsyncPostgresSaver),
            patch("copilot.jobs.executor.ThingSearchService", return_value=AsyncMock()),
            patch("copilot.jobs.executor.set_active_search_service"),
            patch("copilot.jobs.executor.make_llm", return_value=object()),
            patch("copilot.jobs.executor.build_graph", return_value=graph) as build_graph,
        ):
            result = await runner.run(_job(), trigger={"source": "manual"})
            await runner.close()

        self.assertEqual(result["assistant"], "background result")
        self.assertEqual(conninfo_values, ["conninfo"])
        saver.setup.assert_awaited_once()
        self.assertIs(build_graph.call_args.kwargs["checkpointer"], saver)
        self.assertTrue(saver_context.closed)
        local_tool_names = {tool.name for tool in build_graph.call_args.kwargs["local_tools"]}
        self.assertEqual(local_tool_names, {"get_current_time", "look_at_camera", "run_code"})
        self.assertEqual(
            graph.invocations[0][1],
            {"configurable": {"thread_id": "job:job-1"}},
        )


class _FakeRepo:
    def __init__(self, job: Job) -> None:
        self.job = job
        self.created_runs = []
        self.recorded_results = []
        self.disabled = []

    async def get_job(self, job_id: str) -> Job:
        if job_id != self.job.id:
            raise KeyError(job_id)
        return self.job

    async def create_job_run(
        self,
        *,
        job: Job,
        source: JobRunSource,
        trigger_payload: dict,
        now: datetime,
    ) -> JobRun:
        self.created_runs.append(
            {
                "job": job,
                "source": source,
                "trigger_payload": trigger_payload,
                "now": now,
            }
        )
        return JobRun(
            id="run-1",
            job_id=job.id,
            job_thread_id=job.job_thread_id,
            source=source,
            status=JobRunStatus.RUNNING,
            trigger_payload=trigger_payload,
            started_at=now,
            created_at=now,
        )

    async def record_job_result(self, **kwargs) -> None:
        self.recorded_results.append(kwargs)

    async def disable_job(self, job_id: str) -> None:
        self.disabled.append(job_id)


class _FakePublisher:
    def __init__(self) -> None:
        self.published = []

    async def publish_job_run(self, job_id: str) -> None:
        self.published.append(job_id)


class JobExecutorTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_job_records_response_and_publishes_event(self) -> None:
        repo = _FakeRepo(_job())
        publisher = _FakePublisher()
        agent_runner = AsyncMock()
        agent_runner.run.return_value = {"ok": True, "assistant": "done"}
        executor = JobExecutor(
            Settings(),
            repo=repo,
            agent_runner=agent_runner,
            event_publisher=publisher,
        )

        result = await executor.run_job("job-1", {"source": "manual"})

        self.assertEqual(result["assistant"], "done")
        self.assertEqual(repo.created_runs[0]["source"], JobRunSource.MANUAL)
        self.assertEqual(repo.recorded_results[0]["response_text"], "done")
        self.assertEqual(repo.recorded_results[0]["status"], JobRunStatus.SUCCEEDED)
        self.assertEqual(repo.recorded_results[0]["run_id"], "run-1")
        self.assertEqual(publisher.published, ["job-1"])

    async def test_prompt_job_failure_records_last_error(self) -> None:
        repo = _FakeRepo(_job())
        publisher = _FakePublisher()
        agent_runner = AsyncMock()
        agent_runner.run.side_effect = RuntimeError("boom")
        executor = JobExecutor(
            Settings(),
            repo=repo,
            agent_runner=agent_runner,
            event_publisher=publisher,
        )

        result = await executor.run_job("job-1", {"source": "manual"})

        self.assertFalse(result["ok"])
        self.assertEqual(repo.recorded_results[0]["error"], "boom")
        self.assertEqual(repo.recorded_results[0]["status"], JobRunStatus.FAILED)

    async def test_analysis_job_uses_code_executor(self) -> None:
        repo = _FakeRepo(
            _job(
                action_kind=JobActionKind.ANALYSIS,
                prompt=None,
                analysis_code="print('42')",
            )
        )
        publisher = _FakePublisher()
        code_executor = AsyncMock()
        code_executor.execute.return_value = {"stdout": "WOT_LAST_VALUE=42\n"}
        agent_runner = AsyncMock()
        executor = JobExecutor(
            Settings(),
            repo=repo,
            code_executor_client=code_executor,
            agent_runner=agent_runner,
            event_publisher=publisher,
        )

        result = await executor.run_job("job-1", {"source": "manual"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["last_fetch_value"], "42")
        agent_runner.run.assert_not_called()

    async def test_one_shot_time_job_disabled_after_scheduled_run(self) -> None:
        run_at = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
        repo = _FakeRepo(
            _job(
                schedule_kind=TimeTriggerKind.ONCE,
                run_at=run_at,
                interval_seconds=None,
                next_run_at=run_at,
            )
        )
        agent_runner = AsyncMock()
        agent_runner.run.return_value = {"ok": True, "assistant": "done"}
        executor = JobExecutor(
            Settings(),
            repo=repo,
            agent_runner=agent_runner,
            event_publisher=_FakePublisher(),
        )

        await executor.run_job("job-1", {"source": "time"})

        self.assertEqual(repo.disabled, ["job-1"])

    async def test_interval_time_job_not_disabled_after_run(self) -> None:
        repo = _FakeRepo(_job(interval_seconds=60))
        agent_runner = AsyncMock()
        agent_runner.run.return_value = {"ok": True, "assistant": "done"}
        executor = JobExecutor(
            Settings(),
            repo=repo,
            agent_runner=agent_runner,
            event_publisher=_FakePublisher(),
        )
        now = datetime(2026, 5, 31, 12, 30, tzinfo=timezone.utc)

        with patch("copilot.jobs.executor.utc_now", return_value=now):
            await executor.run_job("job-1", {"source": "time"})

        self.assertEqual(repo.disabled, [])
        self.assertEqual(
            repo.recorded_results[0]["next_run_at"],
            now + timedelta(seconds=60),
        )

    async def test_manual_interval_run_does_not_advance_next_run_at(self) -> None:
        repo = _FakeRepo(_job(interval_seconds=60))
        agent_runner = AsyncMock()
        agent_runner.run.return_value = {"ok": True, "assistant": "done"}
        executor = JobExecutor(
            Settings(),
            repo=repo,
            agent_runner=agent_runner,
            event_publisher=_FakePublisher(),
        )

        await executor.run_job("job-1", {"source": "manual"})

        self.assertIsNone(repo.recorded_results[0]["next_run_at"])


class _FakeScheduleManager:
    def __init__(self, *, add_error=None, remove_error=None) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []
        self.synced = 0
        self.add_error = add_error
        self.remove_error = remove_error

    async def add_job(self, job: Job) -> None:
        self.added.append(job.id)
        if self.add_error is not None:
            raise self.add_error

    async def remove_job(self, job_id: str) -> None:
        self.removed.append(job_id)
        if self.remove_error is not None:
            raise self.remove_error

    async def sync(self) -> None:
        self.synced += 1


class _FakeServiceRepo:
    def __init__(self, job: Job, *, create_error=None, delete_error=None) -> None:
        self.job = job
        self.created = []
        self.deleted: list[str] = []
        self.loaded: list[str] = []
        self.create_error = create_error
        self.delete_error = delete_error

    async def create_job(self, request, *, next_run_at, subscription_id) -> Job:
        if self.create_error is not None:
            raise self.create_error
        self.created.append((request, next_run_at, subscription_id))
        return self.job

    async def get_job(self, job_id: str) -> Job:
        self.loaded.append(job_id)
        return self.job

    async def delete_job(self, job_id: str) -> Job:
        self.deleted.append(job_id)
        if self.delete_error is not None:
            raise self.delete_error
        return self.job


class _FakeServiceRuntimeClient:
    def __init__(self, *, subscribe_response=None, remove_error=None) -> None:
        self.subscribe_response = subscribe_response or {"subscription": {"subscriptionId": "sub-1"}}
        self.remove_error = remove_error
        self.subscribed = []
        self.removed: list[str] = []

    async def subscribe_event(self, **kwargs):
        self.subscribed.append(kwargs)
        return self.subscribe_response

    async def remove_subscription(self, *, subscription_id: str) -> None:
        self.removed.append(subscription_id)
        if self.remove_error is not None:
            raise self.remove_error


class JobServiceTaskiqTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_run_job_now_waits_for_task_result(self) -> None:
        service = JobService(Settings(), repo=_FakeRepo(_job()))
        task_result = SimpleNamespace(is_err=False, return_value={"ok": True}, error=None)
        task = AsyncMock()
        task.wait_result.return_value = task_result

        with patch("copilot.jobs.service.run_job_task.kiq", AsyncMock(return_value=task)):
            result = await service.run_job_now("job-1")

        self.assertEqual(result, {"ok": True})

    async def test_run_job_now_returns_timeout_error(self) -> None:
        service = JobService(Settings(job_task_timeout_seconds=1), repo=_FakeRepo(_job()))
        task = AsyncMock()
        task.wait_result.side_effect = TaskiqResultTimeoutError(timeout=1)

        with patch("copilot.jobs.service.run_job_task.kiq", AsyncMock(return_value=task)):
            result = await service.run_job_now("job-1")

        self.assertEqual(result, {"ok": False, "error": "Job task timed out."})

    async def test_trigger_job_now_enqueues_without_waiting_for_result(self) -> None:
        service = JobService(Settings(), repo=_FakeRepo(_job()))
        task = SimpleNamespace(task_id="task-1", wait_result=AsyncMock())

        with patch("copilot.jobs.service.run_job_task.kiq", AsyncMock(return_value=task)):
            result = await service.trigger_job_now("job-1")

        self.assertEqual(result, {"ok": True, "job_id": "job-1", "task_id": "task-1"})
        task.wait_result.assert_not_called()

    async def test_create_time_job_registers_schedule(self) -> None:
        schedule = _FakeScheduleManager()
        service = JobService(
            Settings(),
            repo=_FakeServiceRepo(_job(interval_seconds=60)),
            schedule_manager=schedule,
        )
        request = CreateJobRequest(
            name="recurring",
            created_from_thread_id="thread-1",
            prompt="check",
            trigger_kind=JobTriggerKind.TIME,
            schedule_kind=TimeTriggerKind.INTERVAL,
            interval_seconds=60,
        )

        created = await service.create_job(request)

        self.assertEqual(created.id, "job-1")
        self.assertEqual(schedule.added, ["job-1"])

    async def test_create_time_job_deletes_record_when_schedule_registration_fails(self) -> None:
        repo = _FakeServiceRepo(_job(interval_seconds=60))
        schedule = _FakeScheduleManager(add_error=RuntimeError("redis down"))
        service = JobService(
            Settings(),
            repo=repo,
            schedule_manager=schedule,
        )
        request = CreateJobRequest(
            name="recurring",
            created_from_thread_id="thread-1",
            prompt="check",
            trigger_kind=JobTriggerKind.TIME,
            schedule_kind=TimeTriggerKind.INTERVAL,
            interval_seconds=60,
        )

        with self.assertRaises(RuntimeError):
            await service.create_job(request)

        self.assertEqual(schedule.added, ["job-1"])
        self.assertEqual(schedule.removed, ["job-1"])
        self.assertEqual(repo.deleted, ["job-1"])

    async def test_create_event_job_removes_subscription_when_insert_fails(self) -> None:
        repo = _FakeServiceRepo(
            _job(
                trigger_kind=JobTriggerKind.EVENT,
                schedule_kind=None,
                interval_seconds=None,
                next_run_at=None,
                subscription_id="sub-1",
            ),
            create_error=RuntimeError("db down"),
        )
        runtime_client = _FakeServiceRuntimeClient()
        service = JobService(
            Settings(),
            repo=repo,
            runtime_client=runtime_client,
            schedule_manager=_FakeScheduleManager(),
        )
        request = CreateJobRequest(
            name="event check",
            created_from_thread_id="thread-1",
            prompt="check",
            trigger_kind=JobTriggerKind.EVENT,
            thing_id="thing-1",
            event_name="changed",
        )

        with self.assertRaises(RuntimeError):
            await service.create_job(request)

        self.assertEqual(runtime_client.subscribed[0]["thing_id"], "thing-1")
        self.assertEqual(runtime_client.removed, ["sub-1"])

    async def test_delete_time_job_removes_schedule(self) -> None:
        schedule = _FakeScheduleManager()
        service = JobService(
            Settings(),
            repo=_FakeServiceRepo(_job(interval_seconds=60)),
            schedule_manager=schedule,
        )

        await service.delete_job("job-1")

        self.assertEqual(schedule.removed, ["job-1"])

    async def test_delete_time_job_keeps_record_when_schedule_cleanup_fails(self) -> None:
        repo = _FakeServiceRepo(_job(interval_seconds=60))
        schedule = _FakeScheduleManager(remove_error=RuntimeError("redis down"))
        service = JobService(
            Settings(),
            repo=repo,
            schedule_manager=schedule,
        )

        with self.assertRaises(RuntimeError):
            await service.delete_job("job-1")

        self.assertEqual(schedule.removed, ["job-1"])
        self.assertEqual(repo.deleted, [])

    async def test_delete_event_job_keeps_record_when_subscription_cleanup_fails(self) -> None:
        repo = _FakeServiceRepo(
            _job(
                trigger_kind=JobTriggerKind.EVENT,
                schedule_kind=None,
                interval_seconds=None,
                next_run_at=None,
                subscription_id="sub-1",
                thing_id="thing-1",
                event_name="changed",
            )
        )
        runtime_client = _FakeServiceRuntimeClient(remove_error=RuntimeError("runtime down"))
        service = JobService(
            Settings(),
            repo=repo,
            runtime_client=runtime_client,
            schedule_manager=_FakeScheduleManager(),
        )

        with self.assertRaises(RuntimeError):
            await service.delete_job("job-1")

        self.assertEqual(runtime_client.removed, ["sub-1"])
        self.assertEqual(repo.deleted, [])


class _FakeScheduleRepo:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    async def list_enabled_time_jobs(self) -> list[Job]:
        return self.jobs


class _FakeScheduleSource:
    def __init__(self, tasks: list[ScheduledTask] | None = None) -> None:
        self.tasks = {task.schedule_id: task for task in (tasks or [])}
        self.added: list[ScheduledTask] = []
        self.deleted: list[str] = []

    async def add_schedule(self, schedule: ScheduledTask) -> None:
        self.added.append(schedule)
        self.tasks[schedule.schedule_id] = schedule

    async def delete_schedule(self, schedule_id: str) -> None:
        self.deleted.append(schedule_id)
        self.tasks.pop(schedule_id, None)

    async def get_schedules(self) -> list[ScheduledTask]:
        return list(self.tasks.values())


class JobScheduleManagerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_interval_job_builds_native_interval_schedule(self) -> None:
        task = scheduled_task_for_job(_job(interval_seconds=60))

        self.assertEqual(task.schedule_id, schedule_id_for_job("job-1"))
        self.assertEqual(task.interval, 60)
        self.assertIsNone(task.time)
        self.assertEqual(task.kwargs, {"job_id": "job-1", "trigger": {"source": "time"}})

    async def test_one_shot_job_builds_time_schedule(self) -> None:
        run_at = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
        task = scheduled_task_for_job(
            _job(
                schedule_kind=TimeTriggerKind.ONCE,
                run_at=run_at,
                interval_seconds=None,
            )
        )

        self.assertEqual(task.time, run_at)
        self.assertIsNone(task.interval)

    async def test_add_and_remove_job(self) -> None:
        source = _FakeScheduleSource()
        manager = JobScheduleManager(source, repo=_FakeScheduleRepo([]))

        await manager.add_job(_job(interval_seconds=60))
        self.assertEqual(
            [task.schedule_id for task in source.added],
            [schedule_id_for_job("job-1")],
        )

        await manager.remove_job("job-1")
        self.assertEqual(source.deleted, [schedule_id_for_job("job-1")])

    async def test_add_job_ignores_event_jobs(self) -> None:
        source = _FakeScheduleSource()
        manager = JobScheduleManager(source, repo=_FakeScheduleRepo([]))

        await manager.add_job(
            _job(
                trigger_kind=JobTriggerKind.EVENT,
                schedule_kind=None,
                interval_seconds=None,
                next_run_at=None,
            )
        )

        self.assertEqual(source.added, [])

    async def test_sync_adds_missing_and_prunes_stale(self) -> None:
        stale = scheduled_task_for_job(_job(id="stale-job", interval_seconds=30))
        source = _FakeScheduleSource([stale])
        manager = JobScheduleManager(
            source,
            repo=_FakeScheduleRepo([_job(interval_seconds=60)]),
        )

        await manager.sync()

        self.assertEqual(
            [task.schedule_id for task in source.added],
            [schedule_id_for_job("job-1")],
        )
        self.assertEqual(source.deleted, [schedule_id_for_job("stale-job")])


class _FakeEventRepo:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs
        self.subscription_updates = []

    async def list_event_jobs_for_subscription(self, subscription_id: str) -> list[Job]:
        return [
            job
            for job in self.jobs
            if job.subscription_id == subscription_id and job.enabled
        ]

    async def list_enabled_event_jobs(self) -> list[Job]:
        return [job for job in self.jobs if job.enabled]

    async def set_subscription_id(self, job_id: str, subscription_id: str | None) -> None:
        self.subscription_updates.append((job_id, subscription_id))


class _FakeRuntimeClient:
    def __init__(self) -> None:
        self.removed = []
        self.subscribed = []

    async def remove_subscription(self, *, subscription_id: str) -> None:
        self.removed.append(subscription_id)

    async def subscribe_event(self, **kwargs):
        self.subscribed.append(kwargs)
        return {"subscription": {"subscriptionId": "new-sub"}}


class _FailingEventRepo:
    async def list_enabled_event_jobs(self) -> list[Job]:
        raise RuntimeError("db down")


class _FakeRedis:
    def __init__(self) -> None:
        self.acked = []

    async def xack(self, stream: str, group: str, entry_id: str) -> None:
        self.acked.append((stream, group, entry_id))


class _FakeLockRedis:
    def __init__(self, *, acquired: bool) -> None:
        self.acquired = acquired
        self.set_calls = []
        self.eval_calls = []
        self.closed = False

    async def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))
        return self.acquired

    async def eval(self, *args):
        self.eval_calls.append(args)
        return 1

    async def aclose(self) -> None:
        self.closed = True


class JobEventConsumerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_startup_syncs_event_subscriptions(self) -> None:
        repo = _FakeEventRepo(
            [
                _job(
                    trigger_kind=JobTriggerKind.EVENT,
                    schedule_kind=None,
                    interval_seconds=None,
                    next_run_at=None,
                    thing_id="thing-1",
                    event_name="overheated",
                    subscription_id="old-sub",
                )
            ]
        )
        runtime_client = _FakeRuntimeClient()
        consumer = JobEventConsumer(
            Settings(),
            repo=repo,
            runtime_client=runtime_client,
        )

        await consumer._sync_event_subscriptions()

        self.assertEqual(runtime_client.removed, ["old-sub"])
        self.assertEqual(runtime_client.subscribed[0]["thing_id"], "thing-1")
        self.assertEqual(repo.subscription_updates, [("job-1", "new-sub")])

    async def test_startup_sync_runs_when_lock_is_acquired(self) -> None:
        repo = _FakeEventRepo(
            [
                _job(
                    trigger_kind=JobTriggerKind.EVENT,
                    schedule_kind=None,
                    interval_seconds=None,
                    next_run_at=None,
                    thing_id="thing-1",
                    event_name="overheated",
                    subscription_id="old-sub",
                )
            ]
        )
        runtime_client = _FakeRuntimeClient()
        consumer = JobEventConsumer(
            Settings(),
            repo=repo,
            runtime_client=runtime_client,
        )
        redis_client = _FakeLockRedis(acquired=True)

        with patch("copilot.jobs.events.redis.from_url", return_value=redis_client):
            await consumer.start()

        self.assertTrue(redis_client.set_calls)
        self.assertEqual(redis_client.set_calls[0][1]["nx"], True)
        self.assertEqual(redis_client.set_calls[0][1]["ex"], 300)
        self.assertEqual(len(redis_client.eval_calls), 1)
        self.assertTrue(redis_client.closed)
        self.assertEqual(runtime_client.removed, ["old-sub"])
        self.assertEqual(repo.subscription_updates, [("job-1", "new-sub")])

    async def test_startup_sync_is_skipped_when_lock_is_held(self) -> None:
        repo = _FakeEventRepo(
            [
                _job(
                    trigger_kind=JobTriggerKind.EVENT,
                    schedule_kind=None,
                    interval_seconds=None,
                    next_run_at=None,
                    thing_id="thing-1",
                    event_name="overheated",
                    subscription_id="old-sub",
                )
            ]
        )
        runtime_client = _FakeRuntimeClient()
        consumer = JobEventConsumer(
            Settings(),
            repo=repo,
            runtime_client=runtime_client,
        )
        redis_client = _FakeLockRedis(acquired=False)

        with patch("copilot.jobs.events.redis.from_url", return_value=redis_client):
            await consumer.start()

        self.assertTrue(redis_client.set_calls)
        self.assertEqual(redis_client.eval_calls, [])
        self.assertTrue(redis_client.closed)
        self.assertEqual(runtime_client.removed, [])
        self.assertEqual(runtime_client.subscribed, [])
        self.assertEqual(repo.subscription_updates, [])

    async def test_startup_sync_releases_lock_when_sync_fails(self) -> None:
        consumer = JobEventConsumer(
            Settings(),
            repo=_FailingEventRepo(),
            runtime_client=_FakeRuntimeClient(),
        )
        redis_client = _FakeLockRedis(acquired=True)

        with (
            patch("copilot.jobs.events.redis.from_url", return_value=redis_client),
            self.assertRaises(RuntimeError),
        ):
            await consumer.start()

        self.assertEqual(len(redis_client.eval_calls), 1)
        self.assertTrue(redis_client.closed)

    async def test_matching_event_enqueues_task_for_subscribed_job(self) -> None:
        consumer = JobEventConsumer(
            Settings(),
            repo=_FakeEventRepo(
                [
                    _job(
                        trigger_kind=JobTriggerKind.EVENT,
                        schedule_kind=None,
                        interval_seconds=None,
                        next_run_at=None,
                        subscription_id="sub-1",
                    )
                ]
            ),
        )

        with patch("copilot.jobs.events.run_job_task.kiq", AsyncMock()) as kiq:
            await consumer._handle_stream_entry(
                {
                    "event_type": "event_received",
                    "thing_id": "thing-1",
                    "name": "overheated",
                    "subscription_id": "sub-1",
                    "payload_base64": "eyJ0ZW1wZXJhdHVyZSI6NDJ9",
                    "content_type": "application/json",
                    "timestamp": "2026-05-31T12:00:00+00:00",
                }
            )

        kiq.assert_awaited_once()
        self.assertEqual(kiq.call_args.kwargs["job_id"], "job-1")
        trigger = kiq.call_args.kwargs["trigger"]
        self.assertEqual(trigger["source"], "event")
        self.assertEqual(trigger["payload_base64"], "eyJ0ZW1wZXJhdHVyZSI6NDJ9")
        self.assertEqual(trigger["content_type"], "application/json")

    async def test_stream_entry_is_not_acked_when_enqueue_fails(self) -> None:
        redis_client = _FakeRedis()
        consumer = JobEventConsumer(
            Settings(wot_runtime_stream="runtime", jobs_events_group="jobs"),
            repo=_FakeEventRepo(
                [
                    _job(
                        trigger_kind=JobTriggerKind.EVENT,
                        schedule_kind=None,
                        interval_seconds=None,
                        next_run_at=None,
                        subscription_id="sub-1",
                    )
                ]
            ),
        )

        with (
            patch(
                "copilot.jobs.events.run_job_task.kiq",
                AsyncMock(side_effect=RuntimeError("enqueue failed")),
            ),
            self.assertRaises(RuntimeError),
        ):
            await consumer._process_entries(
                redis_client,
                [
                    (
                        "1-0",
                        {
                            "event_type": "event_received",
                            "subscription_id": "sub-1",
                        },
                    )
                ],
            )

        self.assertEqual(redis_client.acked, [])


class JobsEventsRouteTestCase(unittest.TestCase):
    def test_run_route_enqueues_job_and_returns_accepted(self) -> None:
        class FakeService:
            def __init__(self) -> None:
                self.triggered: list[str] = []

            async def trigger_job_now(self, job_id):
                self.triggered.append(job_id)
                return {"ok": True, "job_id": job_id}

        fake_service = FakeService()
        app = FastAPI()
        app.state.service = fake_service
        app.include_router(jobs_router)

        with TestClient(app) as client:
            response = client.post("/jobs/job-1/run")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"ok": True, "job_id": "job-1"})
        self.assertEqual(fake_service.triggered, ["job-1"])

    def test_sse_events_include_redis_stream_id(self) -> None:
        class FakeService:
            async def subscribe_run_events(self, *, last_event_id=None):
                self.last_event_id = last_event_id
                yield "1-0", {"job": {"id": "job-1"}}

        fake_service = FakeService()
        app = FastAPI()
        app.state.service = fake_service
        app.include_router(jobs_router)

        with TestClient(app) as client:
            response = client.get("/jobs/events", headers={"Last-Event-ID": "0-0"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("id: 1-0", response.text)
        self.assertIn('"job"', response.text)
        self.assertEqual(fake_service.last_event_id, "0-0")
