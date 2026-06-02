from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from copilot.jobs.models import (
    Job,
    JobInteractionMode,
    JobOutputKind,
    JobRun,
    JobRunStatus,
)


def graph_input_for_run(job: Job, run: JobRun, message: str | None) -> Any:
    if message is None:
        return {"messages": [HumanMessage(content=job_run_prompt(job))]}
    if result_has_pending_interrupt(run.result):
        return Command(resume=str(message))
    # Compatibility for runs that were already waiting before ask_job_user
    # used LangGraph interrupts: append the reply and let the checkpointer
    # carry the prior context instead of resuming a pending interrupt.
    return {"messages": [HumanMessage(content=str(message))]}


def graph_config_for_run(job: Job, run: JobRun, recursion_limit: int) -> dict[str, Any]:
    return {
        "recursion_limit": recursion_limit,
        "configurable": {
            "thread_id": run.job_thread_id,
            "job_id": job.id,
            "run_id": run.id,
            "job_output_kind": job.output_kind.value,
            "record_schema": job.record_schema,
            "record_schema_version": job.record_schema_version,
            "virtual_thing_id": job.virtual_thing_id,
        },
    }


def job_result_from_graph_result(
    result: Any,
    *,
    job: Job,
    message: str | None,
    trigger: dict[str, Any],
) -> dict[str, Any]:
    submitted_record = submitted_record_from_graph_result(result)
    failed_submission = failed_record_submission_from_graph_result(result)
    waiting_question = waiting_question_from_graph_result(result)
    assistant = assistant_text_from_graph_result(result)

    if waiting_question:
        return _waiting_result(result, waiting_question, trigger)
    if (
        job.output_kind == JobOutputKind.STRUCTURED_RECORD
        and submitted_record is None
        and _record_submission_needs_user_repair(failed_submission)
    ):
        error = _record_submission_error(failed_submission)
        return _waiting_result(
            result,
            _record_repair_question(error),
            trigger,
            metadata={"record_submission_error": error},
        )
    if (
        message is None
        and job.interaction_mode == JobInteractionMode.REQUIRED_CHECKIN
        and assistant
    ):
        return _waiting_result(result, assistant, trigger)
    if job.output_kind == JobOutputKind.STRUCTURED_RECORD and submitted_record is None:
        return _failed_result(
            "Structured record job finished without submitting a valid record.",
            result,
            trigger,
        )
    if not assistant and submitted_record is None and message is not None:
        return _failed_result(
            "Prompt job did not produce a response after the user reply.",
            result,
            trigger,
        )
    if not assistant:
        assistant = json.dumps(result, ensure_ascii=True, default=str)[:2000]
    return {
        "ok": True,
        "response": result,
        "assistant": assistant,
        "submitted_record": submitted_record,
        "metadata": {"trigger": trigger},
    }


def job_run_status_from_result(result: dict[str, Any]) -> JobRunStatus:
    if result.get("status") == JobRunStatus.WAITING_FOR_INPUT.value:
        return JobRunStatus.WAITING_FOR_INPUT
    if result.get("status") == JobRunStatus.SKIPPED.value:
        return JobRunStatus.SKIPPED
    if result.get("ok"):
        return JobRunStatus.SUCCEEDED
    return JobRunStatus.FAILED


def assistant_text_from_graph_result(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages")
    if not isinstance(messages, list):
        return ""
    latest_human_index = -1
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            latest_human_index = index
    for message in reversed(messages[latest_human_index + 1 :]):
        if not isinstance(message, AIMessage):
            continue
        return _text_from_message_content(message.content).strip()
    return ""


def waiting_question_from_graph_result(result: Any) -> str | None:
    interrupt_question = _interrupt_question_from_graph_result(result)
    if interrupt_question:
        return interrupt_question

    message = _tool_message_after_latest_human(result, "ask_job_user")
    if message is None:
        return None
    content = message.content
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return content.strip() or None
    if isinstance(content, dict):
        if content.get("status") == "input_received" or "answer" in content:
            return None
        question = content.get("question")
        if isinstance(question, str) and question.strip():
            return question.strip()
    return None


def submitted_record_from_graph_result(result: Any) -> dict[str, Any] | None:
    message = _tool_message_after_latest_human(result, "submit_job_record")
    if message is None:
        return None
    content = _parsed_tool_message_content(message)
    if not isinstance(content, dict) or not content.get("ok"):
        return None
    record = content.get("record")
    return record if isinstance(record, dict) else content


def failed_record_submission_from_graph_result(result: Any) -> dict[str, Any] | None:
    message = _tool_message_after_latest_human(result, "submit_job_record")
    if message is None:
        return None
    content = _parsed_tool_message_content(message)
    if not isinstance(content, dict) or content.get("ok") is not False:
        return None
    return content


def result_has_pending_interrupt(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    metadata = result.get("metadata")
    if isinstance(metadata, dict) and metadata.get("pending_interrupt") is True:
        return True
    response = result.get("response")
    return _graph_result_has_interrupt(response) or _graph_result_has_interrupt(result)


def job_run_prompt(job: Job) -> str:
    if job.output_kind != JobOutputKind.STRUCTURED_RECORD:
        return job.prompt or ""
    schema = json.dumps(job.record_schema or {}, ensure_ascii=True, indent=2)
    return (
        f"{job.prompt or ''}\n\n"
        "## Structured Record Contract\n"
        "This background job must store exactly one validated record before it "
        "finishes successfully. If user input is needed, call ask_job_user and stop. "
        "After receiving enough information, call submit_job_record with data that "
        "matches this JSON Schema. Do not claim success until submit_job_record returns ok=true.\n\n"
        f"JSON Schema:\n{schema}"
    )


def _failed_result(error: str, result: Any, trigger: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "error": error,
        "response": result,
        "metadata": {"trigger": trigger},
    }


def _waiting_result(
    result: Any,
    question: str,
    trigger: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {"trigger": trigger, **(metadata or {})}
    if _graph_result_has_interrupt(result):
        metadata["pending_interrupt"] = True
    return {
        "ok": True,
        "status": JobRunStatus.WAITING_FOR_INPUT.value,
        "response": result,
        "assistant": question,
        "waiting_question": question,
        "metadata": metadata,
    }


def _tool_message_after_latest_human(result: Any, tool_name: str) -> ToolMessage | None:
    if not isinstance(result, dict):
        return None
    messages = result.get("messages")
    if not isinstance(messages, list):
        return None
    latest_human_index = -1
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            latest_human_index = index
    for message in reversed(messages[latest_human_index + 1 :]):
        if isinstance(message, ToolMessage) and message.name == tool_name:
            return message
    return None


def _parsed_tool_message_content(message: ToolMessage) -> Any:
    content = message.content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    return content


def _record_submission_needs_user_repair(submission: dict[str, Any] | None) -> bool:
    if submission is None:
        return False
    error = _record_submission_error(submission)
    return (
        error.startswith("record data failed schema validation")
        or error == "structured record data must be an object"
    )


def _record_submission_error(submission: dict[str, Any] | None) -> str:
    if not isinstance(submission, dict):
        return "structured record data did not match the schema"
    error = submission.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    return "structured record data did not match the schema"


def _record_repair_question(error: str) -> str:
    return (
        "I could not store the structured record because the answer did not match "
        f"the required schema: {error}. Please clarify or correct the values."
    )


def _graph_result_has_interrupt(result: Any) -> bool:
    return bool(_interrupt_values_from_graph_result(result))


def _interrupt_question_from_graph_result(result: Any) -> str | None:
    for value in _interrupt_values_from_graph_result(result):
        question = _question_from_interrupt_value(value)
        if question:
            return question
    return None


def _interrupt_values_from_graph_result(result: Any) -> list[Any]:
    if not isinstance(result, dict):
        return []
    interrupts = result.get("__interrupt__")
    if not isinstance(interrupts, (list, tuple)):
        return []

    values: list[Any] = []
    for interrupt in interrupts:
        if isinstance(interrupt, dict) and "value" in interrupt:
            values.append(interrupt.get("value"))
        elif hasattr(interrupt, "value"):
            values.append(getattr(interrupt, "value"))
        else:
            values.append(interrupt)
    return values


def _question_from_interrupt_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return None
    for key in ("question", "message", "instruction"):
        question = value.get(key)
        if isinstance(question, str) and question.strip():
            return question.strip()
    return None


def _text_from_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    text_parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text_parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            text_parts.append(item["text"])
    return "".join(text_parts)
