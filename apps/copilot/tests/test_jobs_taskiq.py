from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from taskiq import ScheduledTask
from taskiq.exceptions import TaskiqResultTimeoutError

from copilot.core.settings import Settings
from copilot.jobs.events import JobEventConsumer
from copilot.jobs.executor import (
    BackgroundAgentRunner,
    JobExecutor,
)
from copilot.jobs.graph_results import (
    assistant_text_from_graph_result,
    waiting_question_from_graph_result,
)
from copilot.jobs.models import (
    CreateJobRequest,
    Job,
    JobActionKind,
    JobInteractionMode,
    JobOutputKind,
    JobRun,
    JobRunEvent,
    JobRunEventType,
    JobRunSource,
    JobRunStatus,
    JobTriggerKind,
    TimeTriggerKind,
    UpdateJobRequest,
)
from copilot.jobs.routes import router as jobs_router
from copilot.jobs.routes import _messages_from_job_run_events
from copilot.jobs.resources import JobResourceManager
from copilot.jobs.schedule import (
    JobScheduleManager,
    schedule_id_for_job,
    scheduled_task_for_job,
)
from copilot.jobs.record_summary import submitted_record_event_message
from copilot.jobs.service import JobService
from copilot.jobs.store import JobNotWaitingForInput
from copilot.agent.tools.submit_job_record import submit_job_record


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
    }
    values.update(overrides)
    return Job(**values)


class _FakeGraph:
    def __init__(self) -> None:
        self.configs = []
        self.invocations = []
        self.state_updates = []
        self.response = {"messages": [AIMessage(content="background result")]}

    def with_config(self, **config):
        self.configs.append(config)
        return self

    async def aupdate_state(self, config, values):
        self.state_updates.append((config, values))
        return config

    async def ainvoke(self, input_data, config):
        self.invocations.append((input_data, config))
        return self.response


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
        saver = SimpleNamespace(setup=AsyncMock(), adelete_thread=AsyncMock())
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
            patch(
                "copilot.jobs.executor.build_background_job_graph",
                return_value=graph,
            ) as build_job_graph,
        ):
            result = await runner.run(
                _job(),
                run=JobRun(
                    id="run-1",
                    job_id="job-1",
                    job_thread_id="job:job-1:run:run-1",
                    source=JobRunSource.MANUAL,
                    status=JobRunStatus.RUNNING,
                    trigger_payload={"source": "manual"},
                    started_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
                    created_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
                ),
                trigger={"source": "manual"},
            )
            await runner.close()

        self.assertEqual(result["assistant"], "background result")
        self.assertEqual(conninfo_values, ["conninfo"])
        saver.setup.assert_awaited_once()
        self.assertIs(build_job_graph.call_args.kwargs["checkpointer"], saver)
        self.assertTrue(saver_context.closed)
        self.assertEqual(graph.configs, [])
        local_tool_names = {tool.name for tool in build_job_graph.call_args.kwargs["local_tools"]}
        self.assertEqual(
            local_tool_names,
            {
                "ask_job_user",
                "get_current_time",
                "look_at_camera",
                "run_code",
                "submit_job_record",
            },
        )
        self.assertEqual(
            graph.invocations[0][1],
            {
                "recursion_limit": Settings().recursion_limit,
                "configurable": {
                    "thread_id": "job:job-1:run:run-1",
                    "job_id": "job-1",
                    "run_id": "run-1",
                    "job_output_kind": "narrative",
                    "record_schema": None,
                    "record_schema_version": None,
                    "virtual_thing_id": None,
                },
            },
        )
        self.assertEqual(graph.state_updates, [])

    async def test_legacy_user_reply_appends_to_existing_run_thread(self) -> None:
        graph = _FakeGraph()
        runner = BackgroundAgentRunner(Settings(openai_api_key="test"))
        saver = SimpleNamespace(setup=AsyncMock(), adelete_thread=AsyncMock())
        saver_context = _FakeSaverContext(saver)

        class FakeAsyncPostgresSaver:
            @staticmethod
            def from_conn_string(_conninfo):
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
            patch("copilot.jobs.executor.build_background_job_graph", return_value=graph),
        ):
            await runner.run(
                _job(active_run_id="run-1"),
                run=JobRun(
                    id="run-1",
                    job_id="job-1",
                    job_thread_id="job:job-1:run:run-1",
                    source=JobRunSource.MANUAL,
                    status=JobRunStatus.RUNNING,
                    trigger_payload={"source": "user_reply", "message": "42"},
                    started_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
                    created_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
                ),
                trigger={"source": "user_reply", "message": "42", "previous_run_id": "run-1"},
            )
            await runner.close()

        self.assertEqual(graph.state_updates, [])
        invocation_messages = graph.invocations[0][0]["messages"]
        self.assertEqual(len(invocation_messages), 1)
        # The reply is appended verbatim; the checkpointer carries prior context.
        self.assertEqual(invocation_messages[0].content, "42")
        self.assertEqual(
            graph.invocations[0][1]["configurable"]["thread_id"], "job:job-1:run:run-1"
        )
        saver.adelete_thread.assert_not_awaited()

    async def test_structured_record_reply_resumes_pending_interrupt(self) -> None:
        graph = _FakeGraph()
        graph.response = {
            "messages": [
                ToolMessage(
                    content=(
                        '{"ok": true, "record": {"data": {"feeling": "tired", '
                        '"energy": 2, "note": "headache"}}}'
                    ),
                    name="submit_job_record",
                    tool_call_id="call-1",
                ),
                AIMessage(content="Stored the wellbeing record."),
            ]
        }
        runner = BackgroundAgentRunner(Settings(openai_api_key="test"))
        saver = SimpleNamespace(setup=AsyncMock(), adelete_thread=AsyncMock())
        saver_context = _FakeSaverContext(saver)

        class FakeAsyncPostgresSaver:
            @staticmethod
            def from_conn_string(_conninfo):
                return saver_context

        schema = {
            "type": "object",
            "required": ["feeling", "energy"],
            "properties": {
                "feeling": {"type": "string"},
                "energy": {"type": "integer", "minimum": 1, "maximum": 5},
                "note": {"type": "string"},
            },
            "additionalProperties": False,
        }

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
            patch("copilot.jobs.executor.build_background_job_graph", return_value=graph),
        ):
            result = await runner.run(
                _job(
                    active_run_id="run-1",
                    interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
                    output_kind=JobOutputKind.STRUCTURED_RECORD,
                    record_schema=schema,
                    record_schema_version=1,
                    virtual_thing_id="virtual:records:wellbeing",
                ),
                run=JobRun(
                    id="run-1",
                    job_id="job-1",
                    job_thread_id="job:job-1:run:run-1",
                    source=JobRunSource.TIME,
                    status=JobRunStatus.RUNNING,
                    trigger_payload={
                        "source": "user_reply",
                        "message": "2, tired and headache",
                    },
                    result={"metadata": {"pending_interrupt": True}},
                    started_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
                    created_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
                ),
                trigger={
                    "source": "user_reply",
                    "message": "2, tired and headache",
                    "previous_run_id": "run-1",
                },
            )
            await runner.close()

        saver.adelete_thread.assert_not_awaited()
        invocation_input = graph.invocations[0][0]
        self.assertIsInstance(invocation_input, Command)
        self.assertEqual(invocation_input.resume, "2, tired and headache")
        self.assertEqual(
            graph.invocations[0][1]["configurable"]["thread_id"],
            "job:job-1:run:run-1",
        )
        self.assertEqual(
            graph.invocations[0][1]["configurable"]["virtual_thing_id"],
            "virtual:records:wellbeing",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["submitted_record"]["data"]["energy"], 2)

    async def test_interrupt_payload_is_waiting_result(self) -> None:
        graph = _FakeGraph()
        graph.response = {
            "messages": [AIMessage(content="", tool_calls=[])],
            "__interrupt__": [
                SimpleNamespace(value={"kind": "job_user_input", "question": "Which number?"})
            ],
        }
        runner = BackgroundAgentRunner(Settings(openai_api_key="test"))
        saver = SimpleNamespace(setup=AsyncMock())
        saver_context = _FakeSaverContext(saver)

        class FakeAsyncPostgresSaver:
            @staticmethod
            def from_conn_string(_conninfo):
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
            patch("copilot.jobs.executor.build_background_job_graph", return_value=graph),
        ):
            result = await runner.run(
                _job(),
                run=JobRun(
                    id="run-1",
                    job_id="job-1",
                    job_thread_id="job:job-1:run:run-1",
                    source=JobRunSource.MANUAL,
                    status=JobRunStatus.RUNNING,
                    trigger_payload={"source": "manual"},
                    started_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
                    created_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
                ),
                trigger={"source": "manual"},
            )
            await runner.close()

        self.assertEqual(result["status"], JobRunStatus.WAITING_FOR_INPUT.value)
        self.assertEqual(result["waiting_question"], "Which number?")
        self.assertTrue(result["metadata"]["pending_interrupt"])

    async def test_required_checkin_plain_question_is_waiting(self) -> None:
        graph = _FakeGraph()
        graph.response = {"messages": [AIMessage(content="Which number?")]}
        runner = BackgroundAgentRunner(Settings(openai_api_key="test"))
        saver = SimpleNamespace(setup=AsyncMock())
        saver_context = _FakeSaverContext(saver)

        class FakeAsyncPostgresSaver:
            @staticmethod
            def from_conn_string(_conninfo):
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
            patch("copilot.jobs.executor.build_background_job_graph", return_value=graph),
        ):
            result = await runner.run(
                _job(interaction_mode=JobInteractionMode.REQUIRED_CHECKIN),
                run=JobRun(
                    id="run-1",
                    job_id="job-1",
                    job_thread_id="job:job-1:run:run-1",
                    source=JobRunSource.MANUAL,
                    status=JobRunStatus.RUNNING,
                    trigger_payload={"source": "manual"},
                    started_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
                    created_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
                ),
                trigger={"source": "manual"},
            )
            await runner.close()

        self.assertEqual(result["status"], JobRunStatus.WAITING_FOR_INPUT.value)
        self.assertEqual(result["waiting_question"], "Which number?")

    async def test_waiting_detection_ignores_old_ask_after_user_reply(self) -> None:
        result = {
            "messages": [
                HumanMessage(content="first run"),
                ToolMessage(
                    content='{"question": "Which room?"}',
                    name="ask_job_user",
                    tool_call_id="call-1",
                ),
                HumanMessage(content="kitchen"),
                AIMessage(content="done"),
            ]
        }

        self.assertIsNone(waiting_question_from_graph_result(result))

    async def test_waiting_detection_ignores_resumed_ask_tool_result(self) -> None:
        result = {
            "messages": [
                HumanMessage(content="first run"),
                ToolMessage(
                    content=(
                        '{"status": "input_received", "question": "Which room?", '
                        '"answer": "kitchen"}'
                    ),
                    name="ask_job_user",
                    tool_call_id="call-1",
                ),
                AIMessage(content="done"),
            ]
        }

        self.assertIsNone(waiting_question_from_graph_result(result))

    async def test_assistant_text_ignores_old_answer_before_latest_user_reply(self) -> None:
        result = {
            "messages": [
                HumanMessage(content="first run"),
                AIMessage(content="Which room?"),
                HumanMessage(content="kitchen"),
            ]
        }

        self.assertEqual(assistant_text_from_graph_result(result), "")


class JobRunEventMessageTestCase(unittest.TestCase):
    def test_job_run_events_convert_to_thread_messages(self) -> None:
        created_at = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
        messages = _messages_from_job_run_events(
            [
                JobRunEvent(
                    id=1,
                    job_id="job-1",
                    run_id="run-1",
                    event_type=JobRunEventType.RUN_STARTED,
                    created_at=created_at,
                ),
                JobRunEvent(
                    id=2,
                    job_id="job-1",
                    run_id="run-1",
                    event_type=JobRunEventType.USER_REPLY,
                    message="21 C",
                    created_at=created_at,
                ),
                JobRunEvent(
                    id=3,
                    job_id="job-1",
                    run_id="run-1",
                    event_type=JobRunEventType.WAITING_FOR_INPUT,
                    message="Which temperature?",
                    created_at=created_at,
                ),
                JobRunEvent(
                    id=4,
                    job_id="job-1",
                    run_id="run-1",
                    event_type=JobRunEventType.RECORD_SUBMITTED,
                    message="Structured record submitted.",
                    payload={"data": {"mood": "good", "energy": 4}},
                    created_at=created_at,
                ),
            ]
        )

        self.assertEqual(
            [message["role"] for message in messages],
            ["system", "user", "assistant", "system"],
        )
        self.assertEqual(messages[0]["content"], "Run started.")
        self.assertEqual(messages[1]["content"], "21 C")
        self.assertEqual(messages[2]["jobEventType"], "waiting_for_input")
        self.assertEqual(
            messages[3]["content"],
            "Structured record submitted: mood=good, energy=4",
        )

    def test_submitted_record_event_message_summarizes_record_data(self) -> None:
        self.assertEqual(
            submitted_record_event_message(
                {"data": {"mood": "good", "energy": 4, "note": "slept well"}}
            ),
            "Structured record submitted: mood=good, energy=4, note=slept well",
        )


class _FakeRepo:
    def __init__(self, job: Job, *, duplicate_reply: bool = False) -> None:
        self.job = job
        self.duplicate_reply = duplicate_reply
        self.started_runs = []
        self.finished_runs = []
        self.disabled = []

    async def get_job(self, job_id: str) -> Job:
        if job_id != self.job.id:
            raise KeyError(job_id)
        return self.job

    async def try_start_job_run(
        self,
        *,
        job_id: str,
        source: JobRunSource,
        trigger_payload: dict,
        now: datetime,
    ) -> JobRun | None:
        self.started_runs.append(
            {
                "job_id": job_id,
                "source": source,
                "trigger_payload": trigger_payload,
                "now": now,
            }
        )
        return JobRun(
            id="run-1",
            job_id=self.job.id,
            job_thread_id=f"{self.job.job_thread_id}:run:run-1",
            source=source,
            status=JobRunStatus.RUNNING,
            trigger_payload=trigger_payload,
            started_at=now,
            created_at=now,
        )

    async def start_reply_job_run(
        self,
        *,
        job_id: str,
        message: str,
        client_reply_id: str | None,
        previous_run_id: str | None,
        now: datetime,
    ) -> JobRun:
        self.started_runs.append(
            {
                "job_id": job_id,
                "source": JobRunSource.MANUAL,
                "trigger_payload": {
                    "source": "user_reply",
                    "message": message,
                    "client_reply_id": client_reply_id,
                    "previous_run_id": previous_run_id,
                },
                "now": now,
            }
        )
        trigger_payload = {
            "source": "user_reply",
            "message": message,
            "client_reply_id": client_reply_id,
        }
        if self.duplicate_reply:
            trigger_payload["_duplicate_reply"] = True
        return JobRun(
            id=previous_run_id or self.job.active_run_id or "run-1",
            job_id=self.job.id,
            job_thread_id=(
                f"{self.job.job_thread_id}:run:{previous_run_id or self.job.active_run_id or 'run-1'}"
            ),
            source=self.job.active_run_source or JobRunSource.MANUAL,
            status=JobRunStatus.SUCCEEDED if self.duplicate_reply else JobRunStatus.RUNNING,
            trigger_payload=trigger_payload,
            result={"ok": True, "assistant": "continued"} if self.duplicate_reply else None,
            response_text="continued" if self.duplicate_reply else None,
            started_at=now,
            created_at=now,
        )

    async def finish_job_run(self, **kwargs) -> None:
        self.finished_runs.append(kwargs)

    async def disable_job(self, job_id: str) -> None:
        self.disabled.append(job_id)


class _FakePublisher:
    def __init__(self) -> None:
        self.published = []

    async def publish_job_run(self, job_id: str, *, run_id: str | None = None) -> None:
        self.published.append((job_id, run_id))


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
        self.assertEqual(repo.started_runs[0]["source"], JobRunSource.MANUAL)
        self.assertEqual(repo.finished_runs[0]["response_text"], "done")
        self.assertEqual(repo.finished_runs[0]["status"], JobRunStatus.SUCCEEDED)
        self.assertEqual(repo.finished_runs[0]["run_id"], "run-1")
        self.assertEqual(publisher.published, [("job-1", "run-1")])

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
        self.assertEqual(repo.finished_runs[0]["error"], "boom")
        self.assertEqual(repo.finished_runs[0]["status"], JobRunStatus.FAILED)

    async def test_prompt_job_waiting_result_records_waiting_question(self) -> None:
        repo = _FakeRepo(_job())
        agent_runner = AsyncMock()
        agent_runner.run.return_value = {
            "ok": True,
            "status": "waiting_for_input",
            "assistant": "Which temperature?",
            "waiting_question": "Which temperature?",
        }
        executor = JobExecutor(
            Settings(),
            repo=repo,
            agent_runner=agent_runner,
            event_publisher=_FakePublisher(),
        )

        await executor.run_job("job-1", {"source": "manual"})

        self.assertEqual(
            repo.finished_runs[0]["status"],
            JobRunStatus.WAITING_FOR_INPUT,
        )
        self.assertEqual(repo.finished_runs[0]["waiting_question"], "Which temperature?")

    async def test_duplicate_reply_run_does_not_resume_agent(self) -> None:
        repo = _FakeRepo(
            _job(
                last_run_id="run-1",
                active_run_id="run-1",
                last_run_status=JobRunStatus.WAITING_FOR_INPUT,
            ),
            duplicate_reply=True,
        )
        publisher = _FakePublisher()
        agent_runner = AsyncMock()
        executor = JobExecutor(
            Settings(),
            repo=repo,
            agent_runner=agent_runner,
            event_publisher=publisher,
        )

        result = await executor.run_job(
            "job-1",
            {
                "source": "user_reply",
                "message": "kitchen",
                "client_reply_id": "reply-1",
                "previous_run_id": "run-1",
            },
        )

        self.assertEqual(result["status"], "duplicate_reply")
        self.assertEqual(result["result"], {"ok": True, "assistant": "continued"})
        agent_runner.run.assert_not_called()
        self.assertEqual(repo.finished_runs, [])
        self.assertEqual(publisher.published, [("job-1", "run-1")])

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
        code_executor.execute.return_value = {
            "stdout": '{"observed_value": 42, "summary": "ok"}\n',
            "images": ["image-1.png"],
            "plotly": ["chart-1.json"],
        }
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
        self.assertEqual(
            result["response"]["stdout"],
            '{"observed_value": 42, "summary": "ok"}\n',
        )
        self.assertEqual(result["stdout"], '{"observed_value": 42, "summary": "ok"}')
        self.assertEqual(
            result["artifacts"],
            [
                {
                    "ref": "image_1",
                    "kind": "image",
                    "filename": "image-1.png",
                },
                {
                    "ref": "chart_1",
                    "kind": "plotly",
                    "filename": "chart-1.json",
                },
            ],
        )
        self.assertIn("1 chart", result["assistant"])
        self.assertIn("1 image", result["assistant"])
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
            repo.finished_runs[0]["next_run_at"],
            now + timedelta(seconds=60),
        )

    async def test_cron_time_job_advances_next_run_at_after_run(self) -> None:
        repo = _FakeRepo(
            _job(
                schedule_kind=TimeTriggerKind.CRON,
                interval_seconds=None,
                cron_expression="0 9 * * sun",
                cron_timezone="Europe/Berlin",
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
        now = datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc)

        with patch("copilot.jobs.executor.utc_now", return_value=now):
            await executor.run_job("job-1", {"source": "time"})

        self.assertEqual(repo.disabled, [])
        self.assertEqual(
            repo.finished_runs[0]["next_run_at"],
            datetime(2026, 6, 7, 7, 0, tzinfo=timezone.utc),
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

        self.assertIsNone(repo.finished_runs[0]["next_run_at"])

    async def test_submit_job_record_tool_uses_runtime_config(self) -> None:
        class FakeRecordStore:
            def submit_record(self, **kwargs):
                return {"id": "record-1", **kwargs}

        with patch(
            "copilot.agent.tools.submit_job_record.VirtualRecordStore",
            return_value=FakeRecordStore(),
        ):
            result = await submit_job_record.ainvoke(
                {
                    "data": {"mood": "good"},
                    "raw_input": "good",
                    "confidence": 0.9,
                },
                config={
                    "configurable": {
                        "job_id": "job-1",
                        "run_id": "run-1",
                        "virtual_thing_id": "virtual:records:mood",
                    }
                },
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["record"]["thing_id"], "virtual:records:mood")
        self.assertEqual(result["record"]["source_run_id"], "run-1")

    async def test_submit_job_record_tool_marks_schema_errors_repairable(self) -> None:
        class FakeRecordStore:
            def submit_record(self, **kwargs):
                raise ValueError("record data failed schema validation at energy")

        with patch(
            "copilot.agent.tools.submit_job_record.VirtualRecordStore",
            return_value=FakeRecordStore(),
        ):
            result = await submit_job_record.ainvoke(
                {"data": {"energy": "high"}},
                config={
                    "configurable": {
                        "job_id": "job-1",
                        "run_id": "run-1",
                        "virtual_thing_id": "virtual:records:mood",
                    }
                },
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["repairable"])
        self.assertIn("energy", result["error"])

    async def test_submit_job_record_tool_marks_context_errors_not_repairable(self) -> None:
        result = await submit_job_record.ainvoke(
            {"data": {"mood": "good"}},
            config={"configurable": {"job_id": "job-1"}},
        )

        self.assertFalse(result["ok"])
        self.assertFalse(result["repairable"])


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
    def __init__(
        self,
        job: Job,
        *,
        create_error=None,
        delete_error=None,
        jobs: list[Job] | None = None,
        duplicate_reply_run: JobRun | None = None,
    ) -> None:
        self.job = job
        self.jobs = [job] if jobs is None else jobs
        self.created = []
        self.deleted: list[str] = []
        self.loaded: list[str] = []
        self.loaded_by_thread: list[str] = []
        self.loaded_by_client_reply_id: list[tuple[str, str]] = []
        self.updated = []
        self.subscription_updates = []
        self.resource_health_updates = []
        self.create_error = create_error
        self.delete_error = delete_error
        self.duplicate_reply_run = duplicate_reply_run

    async def create_job(self, request, *, next_run_at, subscription_id) -> Job:
        if self.create_error is not None:
            raise self.create_error
        self.created.append((request, next_run_at, subscription_id))
        return self.job

    async def get_job(self, job_id: str) -> Job:
        self.loaded.append(job_id)
        if job_id != self.job.id:
            raise KeyError(job_id)
        return self.job

    async def get_job_by_thread_id(self, job_thread_id: str) -> Job:
        self.loaded_by_thread.append(job_thread_id)
        if job_thread_id != self.job.job_thread_id:
            raise KeyError(job_thread_id)
        return self.job

    async def get_job_by_thread_id_any(self, job_thread_id: str) -> Job:
        return await self.get_job_by_thread_id(job_thread_id)

    async def list_jobs(self, created_from_thread_id: str | None = None) -> list[Job]:
        if created_from_thread_id is None:
            return self.jobs
        return [job for job in self.jobs if job.created_from_thread_id == created_from_thread_id]

    async def get_job_run_by_client_reply_id(
        self,
        job_id: str,
        client_reply_id: str,
    ) -> JobRun | None:
        self.loaded_by_client_reply_id.append((job_id, client_reply_id))
        return self.duplicate_reply_run

    async def update_job(self, job_id: str, **fields) -> Job:
        self.updated.append((job_id, fields))
        if job_id != self.job.id:
            raise KeyError(job_id)
        self.job = self.job.model_copy(update=fields)
        self.jobs = [self.job if job.id == job_id else job for job in self.jobs]
        return self.job

    async def set_subscription_id(self, job_id: str, subscription_id: str | None) -> None:
        self.subscription_updates.append((job_id, subscription_id))
        if job_id != self.job.id:
            raise KeyError(job_id)
        self.job = self.job.model_copy(update={"subscription_id": subscription_id})
        self.jobs = [self.job if job.id == job_id else job for job in self.jobs]

    async def set_job_resource_health(
        self,
        job_id: str,
        *,
        resource: str,
        status: str,
        message: str | None = None,
    ) -> Job | None:
        self.resource_health_updates.append((job_id, resource, status, message))
        return self.job if job_id == self.job.id else None

    async def delete_job(self, job_id: str) -> Job:
        self.deleted.append(job_id)
        if self.delete_error is not None:
            raise self.delete_error
        return self.job


class _FakeServiceRuntimeClient:
    def __init__(self, *, subscribe_response=None, remove_error=None) -> None:
        self.subscribe_response = subscribe_response or {
            "subscription": {"subscriptionId": "sub-1"}
        }
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


class _FakeRecordStore:
    def __init__(
        self,
        *,
        create_error=None,
        delete_error=None,
        existing: set[str] | None = None,
    ) -> None:
        self.created = []
        self.deleted = []
        self.create_error = create_error
        self.delete_error = delete_error
        self.existing = set(existing or set())

    def thing_exists(self, thing_id: str) -> bool:
        return thing_id in self.existing

    def create_or_update_thing(self, **kwargs):
        self.created.append(kwargs)
        if self.create_error is not None:
            raise self.create_error
        self.existing.add(kwargs["thing_id"])
        return {"thing_id": kwargs["thing_id"]}

    def delete_thing(self, thing_id: str) -> None:
        self.deleted.append(thing_id)
        if self.delete_error is not None:
            raise self.delete_error
        self.existing.discard(thing_id)


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

    async def test_reply_to_waiting_thread_routes_to_matching_waiting_job(self) -> None:
        repo = _FakeServiceRepo(
            _job(
                last_run_id="run-1",
                active_run_id="run-1",
                last_run_status=JobRunStatus.WAITING_FOR_INPUT,
                waiting_question="Which room?",
            )
        )
        service = JobService(Settings(), repo=repo)
        task_result = SimpleNamespace(
            is_err=False,
            return_value={"ok": True, "assistant": "continued"},
            error=None,
        )
        task = AsyncMock()
        task.wait_result.return_value = task_result

        with patch(
            "copilot.jobs.service.run_job_task.kiq",
            AsyncMock(return_value=task),
        ) as enqueue:
            result = await service.reply_to_waiting_thread("job:job-1", "kitchen")

        self.assertEqual(result, {"ok": True, "assistant": "continued"})
        self.assertEqual(repo.loaded_by_thread, ["job:job-1"])
        enqueue.assert_awaited_once_with(
            job_id="job-1",
            trigger={
                "source": "user_reply",
                "message": "kitchen",
                "client_reply_id": None,
                "previous_run_id": "run-1",
            },
        )

    async def test_duplicate_reply_id_returns_existing_run_without_enqueue(self) -> None:
        now = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
        duplicate_run = JobRun(
            id="run-1",
            job_id="job-1",
            job_thread_id="job:job-1:run:run-1",
            source=JobRunSource.MANUAL,
            status=JobRunStatus.SUCCEEDED,
            trigger_payload={
                "source": "user_reply",
                "replies": [{"client_reply_id": "reply-1", "message": "kitchen"}],
            },
            result={"ok": True, "assistant": "continued"},
            response_text="continued",
            started_at=now,
            finished_at=now,
            created_at=now,
        )
        repo = _FakeServiceRepo(
            _job(last_run_id="run-1", last_run_status=JobRunStatus.SUCCEEDED),
            duplicate_reply_run=duplicate_run,
        )
        service = JobService(Settings(), repo=repo)

        with patch("copilot.jobs.service.run_job_task.kiq", AsyncMock()) as enqueue:
            result = await service.reply_to_job(
                "job-1",
                "kitchen",
                client_reply_id="reply-1",
            )

        self.assertEqual(result["status"], "duplicate_reply")
        self.assertEqual(result["result"], {"ok": True, "assistant": "continued"})
        self.assertEqual(repo.loaded_by_client_reply_id, [("job-1", "reply-1")])
        enqueue.assert_not_awaited()

    async def test_reply_to_waiting_thread_ignores_non_waiting_thread(self) -> None:
        repo = _FakeServiceRepo(_job(last_run_status=JobRunStatus.SUCCEEDED))
        service = JobService(Settings(), repo=repo)

        with patch("copilot.jobs.service.run_job_task.kiq", AsyncMock()) as enqueue:
            result = await service.reply_to_waiting_thread("job:job-1", "kitchen")

        self.assertIsNone(result)
        enqueue.assert_not_awaited()

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

    async def test_create_cron_job_defaults_timezone_and_prepares_next_run(self) -> None:
        schedule = _FakeScheduleManager()
        repo = _FakeServiceRepo(
            _job(
                schedule_kind=TimeTriggerKind.CRON,
                interval_seconds=None,
                cron_expression="0 9 * * sun",
                cron_timezone="Europe/Berlin",
            )
        )
        service = JobService(
            Settings(jobs_default_timezone="Europe/Berlin"),
            repo=repo,
            schedule_manager=schedule,
        )
        request = CreateJobRequest(
            name="weekly",
            created_from_thread_id="thread-1",
            prompt="check",
            trigger_kind=JobTriggerKind.TIME,
            schedule_kind=TimeTriggerKind.CRON,
            cron_expression="  0 9 * * sun  ",
        )

        created = await service.create_job(request)

        self.assertEqual(created.id, "job-1")
        saved_request, next_run_at, subscription_id = repo.created[0]
        self.assertEqual(saved_request.cron_expression, "0 9 * * sun")
        self.assertEqual(saved_request.cron_timezone, "Europe/Berlin")
        self.assertIsNotNone(next_run_at)
        self.assertIsNone(subscription_id)
        self.assertEqual(schedule.added, ["job-1"])

    async def test_create_record_prompt_job_creates_virtual_record_thing(self) -> None:
        schedule = _FakeScheduleManager()
        record_store = _FakeRecordStore()
        service = JobService(
            Settings(),
            repo=_FakeServiceRepo(
                _job(
                    interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
                    output_kind=JobOutputKind.STRUCTURED_RECORD,
                    record_schema={"type": "object", "properties": {"mood": {"type": "string"}}},
                    record_schema_version=1,
                    virtual_thing_id="virtual:records:morning",
                )
            ),
            schedule_manager=schedule,
            record_store=record_store,
        )
        request = CreateJobRequest(
            name="morning",
            created_from_thread_id="thread-1",
            interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
            output_kind=JobOutputKind.STRUCTURED_RECORD,
            prompt="ask",
            record_schema={"type": "object", "properties": {"mood": {"type": "string"}}},
            virtual_thing_id="virtual:records:morning",
            virtual_thing_title="Morning Check-in",
            trigger_kind=JobTriggerKind.TIME,
            schedule_kind=TimeTriggerKind.INTERVAL,
            interval_seconds=60,
        )

        created = await service.create_job(request)

        self.assertEqual(created.virtual_thing_id, "virtual:records:morning")
        self.assertEqual(record_store.created[0]["thing_id"], "virtual:records:morning")
        self.assertEqual(record_store.created[0]["title"], "Morning Check-in")

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

    async def test_create_record_job_deletes_db_job_when_virtual_thing_creation_fails(
        self,
    ) -> None:
        repo = _FakeServiceRepo(
            _job(
                interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
                output_kind=JobOutputKind.STRUCTURED_RECORD,
                record_schema={"type": "object", "properties": {"mood": {"type": "string"}}},
                record_schema_version=1,
                virtual_thing_id="virtual:records:morning",
            )
        )
        schedule = _FakeScheduleManager()
        record_store = _FakeRecordStore(create_error=RuntimeError("catalog down"))
        service = JobService(
            Settings(),
            repo=repo,
            schedule_manager=schedule,
            record_store=record_store,
        )
        request = CreateJobRequest(
            name="morning",
            created_from_thread_id="thread-1",
            interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
            output_kind=JobOutputKind.STRUCTURED_RECORD,
            prompt="ask",
            record_schema={"type": "object", "properties": {"mood": {"type": "string"}}},
            virtual_thing_id="virtual:records:morning",
            trigger_kind=JobTriggerKind.TIME,
            schedule_kind=TimeTriggerKind.INTERVAL,
            interval_seconds=60,
        )

        with self.assertRaises(RuntimeError):
            await service.create_job(request)

        self.assertEqual(record_store.created[0]["thing_id"], "virtual:records:morning")
        self.assertEqual(record_store.deleted, ["virtual:records:morning"])
        self.assertEqual(schedule.added, [])
        self.assertEqual(schedule.removed, ["job-1"])
        self.assertEqual(repo.deleted, ["job-1"])

    async def test_create_structured_time_job_deletes_virtual_thing_when_schedule_fails(
        self,
    ) -> None:
        repo = _FakeServiceRepo(
            _job(
                interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
                output_kind=JobOutputKind.STRUCTURED_RECORD,
                record_schema={"type": "object", "properties": {"mood": {"type": "string"}}},
                record_schema_version=1,
                virtual_thing_id="virtual:records:morning",
            )
        )
        schedule = _FakeScheduleManager(add_error=RuntimeError("redis down"))
        record_store = _FakeRecordStore()
        service = JobService(
            Settings(),
            repo=repo,
            schedule_manager=schedule,
            record_store=record_store,
        )
        request = CreateJobRequest(
            name="morning",
            created_from_thread_id="thread-1",
            interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
            output_kind=JobOutputKind.STRUCTURED_RECORD,
            prompt="ask",
            record_schema={"type": "object", "properties": {"mood": {"type": "string"}}},
            virtual_thing_id="virtual:records:morning",
            trigger_kind=JobTriggerKind.TIME,
            schedule_kind=TimeTriggerKind.INTERVAL,
            interval_seconds=60,
        )

        with self.assertRaises(RuntimeError):
            await service.create_job(request)

        self.assertEqual(record_store.created[0]["thing_id"], "virtual:records:morning")
        self.assertEqual(record_store.deleted, ["virtual:records:morning"])
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

    async def test_delete_structured_time_job_removes_schedule_and_virtual_record_thing(
        self,
    ) -> None:
        schedule = _FakeScheduleManager()
        record_store = _FakeRecordStore()
        repo = _FakeServiceRepo(
            _job(
                interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
                output_kind=JobOutputKind.STRUCTURED_RECORD,
                record_schema={"type": "object", "properties": {"mood": {"type": "string"}}},
                record_schema_version=1,
                virtual_thing_id="virtual:records:morning",
            )
        )
        service = JobService(
            Settings(),
            repo=repo,
            schedule_manager=schedule,
            record_store=record_store,
        )

        await service.delete_job("job-1")

        self.assertEqual(schedule.removed, ["job-1"])
        self.assertEqual(record_store.deleted, ["virtual:records:morning"])
        self.assertEqual(repo.deleted, ["job-1"])

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

    async def test_disable_event_job_removes_subscription_and_clears_id(self) -> None:
        repo = _FakeServiceRepo(
            _job(
                trigger_kind=JobTriggerKind.EVENT,
                schedule_kind=None,
                interval_seconds=None,
                next_run_at=None,
                subscription_id="old-sub",
                thing_id="thing-1",
                event_name="changed",
            )
        )
        runtime_client = _FakeServiceRuntimeClient()
        service = JobService(
            Settings(),
            repo=repo,
            runtime_client=runtime_client,
            schedule_manager=_FakeScheduleManager(),
        )

        updated = await service.update_job("job-1", UpdateJobRequest(enabled=False))

        self.assertFalse(updated.enabled)
        self.assertIsNone(updated.subscription_id)
        self.assertEqual(runtime_client.removed, ["old-sub"])
        self.assertEqual(repo.subscription_updates, [("job-1", None)])
        self.assertEqual(
            repo.resource_health_updates,
            [("job-1", "event_subscription", "healthy", None)],
        )

    async def test_disable_event_job_records_degraded_health_when_cleanup_fails(
        self,
    ) -> None:
        repo = _FakeServiceRepo(
            _job(
                trigger_kind=JobTriggerKind.EVENT,
                schedule_kind=None,
                interval_seconds=None,
                next_run_at=None,
                subscription_id="old-sub",
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
            await service.update_job("job-1", UpdateJobRequest(enabled=False))

        self.assertEqual(runtime_client.removed, ["old-sub"])
        self.assertEqual(
            repo.resource_health_updates,
            [("job-1", "event_subscription", "degraded", "runtime down")],
        )

    async def test_enable_event_job_creates_subscription_and_stores_id(self) -> None:
        repo = _FakeServiceRepo(
            _job(
                enabled=False,
                trigger_kind=JobTriggerKind.EVENT,
                schedule_kind=None,
                interval_seconds=None,
                next_run_at=None,
                subscription_id=None,
                thing_id="thing-1",
                event_name="changed",
                subscription_input={"threshold": 3},
            )
        )
        runtime_client = _FakeServiceRuntimeClient()
        service = JobService(
            Settings(),
            repo=repo,
            runtime_client=runtime_client,
            schedule_manager=_FakeScheduleManager(),
        )

        updated = await service.update_job("job-1", UpdateJobRequest(enabled=True))

        self.assertTrue(updated.enabled)
        self.assertEqual(updated.subscription_id, "sub-1")
        self.assertEqual(runtime_client.subscribed[0]["thing_id"], "thing-1")
        self.assertEqual(runtime_client.subscribed[0]["event_name"], "changed")
        self.assertEqual(runtime_client.subscribed[0]["subscription_input"], {"threshold": 3})
        self.assertEqual(repo.subscription_updates, [("job-1", "sub-1")])
        self.assertEqual(
            repo.resource_health_updates,
            [("job-1", "event_subscription", "healthy", None)],
        )


class JobResourceManagerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_sync_record_things_repairs_missing_structured_record_thing(self) -> None:
        record_store = _FakeRecordStore()
        job = _job(
            interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
            output_kind=JobOutputKind.STRUCTURED_RECORD,
            record_schema={"type": "object", "properties": {"mood": {"type": "string"}}},
            record_schema_version=1,
            virtual_thing_id="virtual:records:morning",
        )
        manager = JobResourceManager(
            repo=_FakeServiceRepo(job),
            runtime_client=_FakeServiceRuntimeClient(),
            schedule_manager=_FakeScheduleManager(),
            record_store=record_store,
        )

        repaired = await manager.sync_record_things()

        self.assertEqual(repaired, 1)
        self.assertEqual(record_store.created[0]["thing_id"], "virtual:records:morning")
        self.assertEqual(record_store.created[0]["title"], "Demo job")

    async def test_sync_record_things_keeps_existing_structured_record_thing(self) -> None:
        record_store = _FakeRecordStore(existing={"virtual:records:morning"})
        job = _job(
            interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
            output_kind=JobOutputKind.STRUCTURED_RECORD,
            record_schema={"type": "object", "properties": {"mood": {"type": "string"}}},
            record_schema_version=1,
            virtual_thing_id="virtual:records:morning",
        )
        manager = JobResourceManager(
            repo=_FakeServiceRepo(job),
            runtime_client=_FakeServiceRuntimeClient(),
            schedule_manager=_FakeScheduleManager(),
            record_store=record_store,
        )

        repaired = await manager.sync_record_things()

        self.assertEqual(repaired, 0)
        self.assertEqual(record_store.created, [])

    async def test_sync_repairs_schedules_and_record_things(self) -> None:
        schedule = _FakeScheduleManager()
        record_store = _FakeRecordStore()
        job = _job(
            interaction_mode=JobInteractionMode.REQUIRED_CHECKIN,
            output_kind=JobOutputKind.STRUCTURED_RECORD,
            record_schema={"type": "object", "properties": {"mood": {"type": "string"}}},
            record_schema_version=1,
            virtual_thing_id="virtual:records:morning",
        )
        manager = JobResourceManager(
            repo=_FakeServiceRepo(job),
            runtime_client=_FakeServiceRuntimeClient(),
            schedule_manager=schedule,
            record_store=record_store,
        )

        await manager.sync()

        self.assertEqual(schedule.synced, 1)
        self.assertEqual(record_store.created[0]["thing_id"], "virtual:records:morning")

    async def test_sync_event_subscriptions_replaces_stale_subscription(self) -> None:
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
        manager = JobResourceManager(
            repo=repo,
            runtime_client=runtime_client,
            schedule_manager=_FakeScheduleManager(),
            record_store=_FakeRecordStore(),
        )

        synced = await manager.sync_event_subscriptions()

        self.assertEqual(synced, 1)
        self.assertEqual(runtime_client.removed, ["old-sub"])
        self.assertEqual(runtime_client.subscribed[0]["thing_id"], "thing-1")
        self.assertEqual(repo.subscription_updates, [("job-1", "new-sub")])


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

    async def test_cron_job_builds_native_cron_schedule(self) -> None:
        task = scheduled_task_for_job(
            _job(
                schedule_kind=TimeTriggerKind.CRON,
                interval_seconds=None,
                cron_expression="0 9 * * sun",
                cron_timezone="Europe/Berlin",
            )
        )

        self.assertEqual(task.cron, "0 9 * * sun")
        self.assertEqual(task.cron_offset, "Europe/Berlin")
        self.assertIsNone(task.interval)
        self.assertIsNone(task.time)

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
        self.resource_health_updates = []

    async def list_event_jobs_for_subscription(self, subscription_id: str) -> list[Job]:
        return [job for job in self.jobs if job.subscription_id == subscription_id and job.enabled]

    async def list_enabled_event_jobs(self) -> list[Job]:
        return [job for job in self.jobs if job.enabled]

    async def set_subscription_id(self, job_id: str, subscription_id: str | None) -> None:
        self.subscription_updates.append((job_id, subscription_id))

    async def set_job_resource_health(
        self,
        job_id: str,
        *,
        resource: str,
        status: str,
        message: str | None = None,
    ) -> Job | None:
        self.resource_health_updates.append((job_id, resource, status, message))
        return None


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

    def test_reply_route_returns_conflict_when_job_is_not_waiting(self) -> None:
        class FakeService:
            async def reply_to_job(self, job_id, message, *, client_reply_id=None):
                raise JobNotWaitingForInput(job_id)

        app = FastAPI()
        app.state.service = FakeService()
        app.include_router(jobs_router)

        with TestClient(app) as client:
            response = client.post("/jobs/job-1/reply", json={"message": "continue"})

        self.assertEqual(response.status_code, 409)

    def test_runs_route_returns_job_run_history(self) -> None:
        now = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)

        class FakeService:
            async def list_job_runs(self, job_id):
                return [
                    JobRun(
                        id="run-1",
                        job_id=job_id,
                        job_thread_id="job:job-1",
                        source=JobRunSource.MANUAL,
                        status=JobRunStatus.SKIPPED,
                        trigger_payload={"source": "manual"},
                        started_at=now,
                        finished_at=now,
                        created_at=now,
                    )
                ]

        app = FastAPI()
        app.state.service = FakeService()
        app.include_router(jobs_router)

        with TestClient(app) as client:
            response = client.get("/jobs/job-1/runs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["runs"][0]["status"], "skipped")

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
