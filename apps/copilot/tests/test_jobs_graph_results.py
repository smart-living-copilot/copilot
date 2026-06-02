from __future__ import annotations

import unittest
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from copilot.jobs.graph_results import (
    failed_record_submission_from_graph_result,
    graph_input_for_run,
    job_result_from_graph_result,
    job_run_status_from_result,
    submitted_record_from_graph_result,
    waiting_question_from_graph_result,
)
from copilot.jobs.models import (
    Job,
    JobActionKind,
    JobOutputKind,
    JobRun,
    JobRunSource,
    JobRunStatus,
    JobTriggerKind,
    TimeTriggerKind,
)


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


def _run(**overrides) -> JobRun:
    now = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
    values = {
        "id": "run-1",
        "job_id": "job-1",
        "job_thread_id": "job:job-1:run:run-1",
        "source": JobRunSource.MANUAL,
        "status": JobRunStatus.RUNNING,
        "trigger_payload": {"source": "manual"},
        "started_at": now,
        "created_at": now,
    }
    values.update(overrides)
    return JobRun(**values)


class JobGraphResultsTestCase(unittest.TestCase):
    def test_reply_to_pending_interrupt_uses_command_resume(self) -> None:
        graph_input = graph_input_for_run(
            _job(),
            _run(result={"metadata": {"pending_interrupt": True}}),
            "21 C",
        )

        self.assertIsInstance(graph_input, Command)
        self.assertEqual(graph_input.resume, "21 C")

    def test_waiting_question_prefers_interrupt_payload(self) -> None:
        result = {
            "messages": [AIMessage(content="", tool_calls=[])],
            "__interrupt__": [{"value": {"question": "Which room?"}}],
        }

        self.assertEqual(waiting_question_from_graph_result(result), "Which room?")

    def test_resumed_ask_tool_result_is_not_waiting_again(self) -> None:
        result = {
            "messages": [
                HumanMessage(content="start"),
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

    def test_submitted_record_and_status_are_classified(self) -> None:
        result = {
            "messages": [
                HumanMessage(content="start"),
                ToolMessage(
                    content='{"ok": true, "record": {"data": {"mood": "good"}}}',
                    name="submit_job_record",
                    tool_call_id="call-1",
                ),
                AIMessage(content="Stored."),
            ]
        }

        submitted_record = submitted_record_from_graph_result(result)
        job_result = job_result_from_graph_result(
            result,
            job=_job(output_kind=JobOutputKind.STRUCTURED_RECORD),
            message="good",
            trigger={"source": "user_reply"},
        )

        self.assertEqual(submitted_record["data"], {"mood": "good"})
        self.assertTrue(job_result["ok"])
        self.assertEqual(job_result["submitted_record"]["data"], {"mood": "good"})
        self.assertEqual(job_run_status_from_result(job_result), JobRunStatus.SUCCEEDED)

    def test_failed_record_schema_submission_waits_for_repair(self) -> None:
        result = {
            "messages": [
                HumanMessage(content="energy was very high"),
                ToolMessage(
                    content=(
                        '{"ok": false, "error": "record data failed schema validation '
                        "at energy: 'high' is not of type 'integer'\"}"
                    ),
                    name="submit_job_record",
                    tool_call_id="call-1",
                ),
                AIMessage(content="I could not store the record."),
            ]
        }

        failed_submission = failed_record_submission_from_graph_result(result)
        job_result = job_result_from_graph_result(
            result,
            job=_job(output_kind=JobOutputKind.STRUCTURED_RECORD),
            message="energy was very high",
            trigger={"source": "user_reply"},
        )

        self.assertIsNotNone(failed_submission)
        self.assertTrue(job_result["ok"])
        self.assertEqual(job_result["status"], JobRunStatus.WAITING_FOR_INPUT.value)
        self.assertIn("energy", job_result["waiting_question"])
        self.assertIn("record_submission_error", job_result["metadata"])
        self.assertEqual(job_run_status_from_result(job_result), JobRunStatus.WAITING_FOR_INPUT)

    def test_non_user_repairable_record_tool_error_still_fails(self) -> None:
        result = {
            "messages": [
                HumanMessage(content="good"),
                ToolMessage(
                    content=(
                        '{"ok": false, "error": '
                        '"submit_job_record requires job_id, run_id, and virtual_thing_id"}'
                    ),
                    name="submit_job_record",
                    tool_call_id="call-1",
                ),
                AIMessage(content="I could not store the record."),
            ]
        }

        job_result = job_result_from_graph_result(
            result,
            job=_job(output_kind=JobOutputKind.STRUCTURED_RECORD),
            message="good",
            trigger={"source": "user_reply"},
        )

        self.assertFalse(job_result["ok"])
        self.assertEqual(job_run_status_from_result(job_result), JobRunStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
