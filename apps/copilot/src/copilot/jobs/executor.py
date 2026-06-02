from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:  # pragma: no cover - dependency is installed in the app image.
    AsyncPostgresSaver = None  # type: ignore[assignment]

from copilot.agent import build_background_job_graph
from copilot.agent.tools.ask_job_user import ask_job_user
from copilot.agent.tools.get_current_time import get_current_time
from copilot.agent.tools.look_at_camera import look_at_camera
from copilot.agent.tools.run_code import run_code
from copilot.agent.tools.submit_job_record import submit_job_record
from copilot.agent.tools.wot_registry import REGISTRY_TOOLS
from copilot.core.config import get_settings as get_registry_settings
from copilot.core.database import init_db, psycopg_conninfo
from copilot.core.llm import make_llm
from copilot.core.settings import Settings
from copilot.clients.code_executor import (
    CodeExecutorClient,
    format_code_execution_result,
)
from copilot.jobs.models import (
    Job,
    JobActionKind,
    JobInteractionMode,
    JobOutputKind,
    JobRun,
    JobRunSource,
    JobRunStatus,
    TimeTriggerKind,
)
from copilot.jobs.results import JobRunEventPublisher
from copilot.jobs.store import JobStore, utc_now
from copilot.search import ThingSearchService, set_active_search_service

logger = logging.getLogger(__name__)


class BackgroundAgentRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graph: Any | None = None
        self._checkpointer_context: Any | None = None
        self._checkpointer: Any | None = None
        self._search_service: ThingSearchService | None = None

    async def close(self) -> None:
        set_active_search_service(None)
        if self._checkpointer_context is not None:
            await self._checkpointer_context.__aexit__(None, None, None)
            self._checkpointer_context = None
            self._checkpointer = None
        if self._search_service is not None:
            await self._search_service.close()
            self._search_service = None
        self._graph = None

    async def _ensure_graph(self) -> Any:
        if self._graph is not None:
            return self._graph

        if AsyncPostgresSaver is None:
            raise RuntimeError(
                "Postgres checkpointing requires langgraph-checkpoint-postgres to be installed"
            )

        init_db()
        registry_settings = get_registry_settings()
        self._search_service = ThingSearchService(registry_settings)
        set_active_search_service(self._search_service)
        database_url = self._settings.agent_state_database_url or registry_settings.DATABASE_URL
        self._checkpointer_context = AsyncPostgresSaver.from_conn_string(
            psycopg_conninfo(database_url)
        )
        self._checkpointer = await self._checkpointer_context.__aenter__()
        await self._checkpointer.setup()

        llm = make_llm(self._settings)
        graph = build_background_job_graph(
            llm=llm,
            registry_tools=REGISTRY_TOOLS,
            local_tools=[
                run_code,
                get_current_time,
                look_at_camera,
                ask_job_user,
                submit_job_record,
            ],
            max_tokens=self._settings.max_context_tokens,
            checkpointer=self._checkpointer,
            parallel_tool_calls=self._settings.parallel_tool_calls,
            vision_enabled=self._settings.vision_enabled,
        )
        self._graph = graph
        return self._graph

    async def run(
        self,
        job: Job,
        *,
        run: JobRun,
        trigger: dict[str, Any],
    ) -> dict[str, Any]:
        graph = await self._ensure_graph()
        message = trigger.get("message") if trigger.get("source") == "user_reply" else None
        graph_input = _graph_input_for_run(job, run, message)
        graph_config = _graph_config_for_run(job, run, self._settings.recursion_limit)
        result = await graph.ainvoke(graph_input, config=graph_config)
        return _job_result_from_graph_result(result, job=job, message=message, trigger=trigger)


class JobExecutor:
    def __init__(
        self,
        settings: Settings,
        *,
        repo: JobStore | None = None,
        code_executor_client: CodeExecutorClient | None = None,
        agent_runner: BackgroundAgentRunner | None = None,
        event_publisher: JobRunEventPublisher | None = None,
    ) -> None:
        self._settings = settings
        self._repo = repo or JobStore()
        self._code_executor_client = code_executor_client or CodeExecutorClient(settings)
        self._agent_runner = agent_runner or BackgroundAgentRunner(settings)
        self._event_publisher = event_publisher or JobRunEventPublisher(settings, repo=self._repo)

    async def close(self) -> None:
        await self._agent_runner.close()

    async def reconcile_stale_running_runs(self) -> int:
        stale_after_seconds = getattr(
            self._settings,
            "job_run_stale_after_seconds",
            max(self._settings.job_task_timeout_seconds * 2, 600),
        )
        cutoff = utc_now() - timedelta(seconds=stale_after_seconds)
        stale_count = await self._repo.mark_stale_running_runs_failed(cutoff=cutoff)
        if stale_count:
            logger.warning("Marked %d stale job run(s) failed on worker startup", stale_count)
        return stale_count

    async def run_job(self, job_id: str, trigger: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        if trigger.get("source") == "user_reply":
            run = await self._repo.start_reply_job_run(
                job_id=job_id,
                message=str(trigger.get("message") or ""),
                previous_run_id=trigger.get("previous_run_id"),
                now=now,
            )
            run_source = run.source
        else:
            run_source = _run_source_from_trigger(trigger)
            run = await self._repo.try_start_job_run(
                job_id=job_id,
                source=run_source,
                trigger_payload=trigger,
                now=now,
            )

        if run is None:
            return {"ok": False, "error": "Job run was not started."}

        if run.status == JobRunStatus.SKIPPED:
            await self._event_publisher.publish_job_run(job_id, run_id=run.id)
            return {
                "ok": False,
                "status": JobRunStatus.SKIPPED.value,
                "job_id": job_id,
                "run_id": run.id,
                "error": run.error or "Job run skipped.",
                "assistant": run.response_text,
            }

        job = await self._repo.get_job(job_id)

        if job.action_kind == JobActionKind.ANALYSIS:
            result = await self._run_analysis_job(job, trigger=trigger)
        else:
            result = await self._run_prompt_job(job, run=run, trigger=trigger)

        now = utc_now()
        is_scheduled_time_run = run_source == JobRunSource.TIME
        next_run_at = (
            now + timedelta(seconds=job.interval_seconds)
            if is_scheduled_time_run and job.interval_seconds is not None
            else None
        )
        status = _job_run_status_from_result(result)

        await self._repo.finish_job_run(
            run_id=run.id,
            job_id=job.id,
            now=now,
            status=status,
            error=result.get("error"),
            response_text=result.get("assistant"),
            result=result,
            next_run_at=next_run_at,
            waiting_question=result.get("waiting_question"),
        )
        # A one-shot time job has fired its only run; disable it so startup
        # reconciliation does not re-create a schedule for it. The Redis schedule
        # itself is removed automatically by the source's post_send.
        if is_scheduled_time_run and job.schedule_kind == TimeTriggerKind.ONCE:
            await self._repo.disable_job(job.id)
        await self._event_publisher.publish_job_run(job.id, run_id=run.id)
        return result

    async def _run_prompt_job(
        self,
        job: Job,
        *,
        run: JobRun,
        trigger: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return await self._agent_runner.run(job, run=run, trigger=trigger)
        except Exception as exc:
            logger.error("Failed prompt job %s: %s", job.id, exc, exc_info=exc)
            return {"ok": False, "error": str(exc), "metadata": {"trigger": trigger}}

    async def _run_analysis_job(self, job: Job, *, trigger: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._code_executor_client.execute(
                session_id=f"job-analysis:{job.id}",
                code=job.analysis_code or "",
            )
            formatted = format_code_execution_result(response)
            stdout = str(formatted.get("stdout", "")).strip()
            artifacts = formatted.get("artifacts", [])

            parts: list[str] = []
            if stdout and stdout != "(no output)":
                parts.append(stdout)
            if isinstance(artifacts, list) and artifacts:
                parts.append(_artifact_summary(artifacts))
            if not parts:
                parts.append("(no output)")

            return {
                "ok": True,
                "response": response,
                **formatted,
                "assistant": "\n".join(parts)[:4000],
                "metadata": {"trigger": trigger},
            }
        except Exception as exc:
            logger.error("Failed analysis job %s: %s", job.id, exc, exc_info=exc)
            return {"ok": False, "error": str(exc), "metadata": {"trigger": trigger}}


def _artifact_summary(artifacts: list[Any]) -> str:
    images = 0
    charts = 0
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("kind") == "image":
            images += 1
        elif artifact.get("kind") == "plotly":
            charts += 1

    parts: list[str] = []
    if charts:
        parts.append(f"{charts} chart{'s' if charts != 1 else ''}")
    if images:
        parts.append(f"{images} image{'s' if images != 1 else ''}")
    return ", ".join(parts)


def _graph_input_for_run(job: Job, run: JobRun, message: str | None) -> Any:
    if message is None:
        return {"messages": [HumanMessage(content=_job_run_prompt(job))]}
    if _result_has_pending_interrupt(run.result):
        return Command(resume=str(message))
    # Compatibility for runs that were already waiting before ask_job_user
    # used LangGraph interrupts: append the reply and let the checkpointer
    # carry the prior context instead of resuming a pending interrupt.
    return {"messages": [HumanMessage(content=str(message))]}


def _graph_config_for_run(job: Job, run: JobRun, recursion_limit: int) -> dict[str, Any]:
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


def _job_result_from_graph_result(
    result: Any,
    *,
    job: Job,
    message: str | None,
    trigger: dict[str, Any],
) -> dict[str, Any]:
    submitted_record = _submitted_record_from_graph_result(result)
    waiting_question = _waiting_question_from_graph_result(result)
    assistant = _assistant_text_from_graph_result(result)

    if waiting_question:
        return _waiting_result(result, waiting_question, trigger)
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
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"trigger": trigger}
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


def _assistant_text_from_graph_result(result: Any) -> str:
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


def _waiting_question_from_graph_result(result: Any) -> str | None:
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


def _result_has_pending_interrupt(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    metadata = result.get("metadata")
    if isinstance(metadata, dict) and metadata.get("pending_interrupt") is True:
        return True
    response = result.get("response")
    return _graph_result_has_interrupt(response) or _graph_result_has_interrupt(result)


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


def _submitted_record_from_graph_result(result: Any) -> dict[str, Any] | None:
    message = _tool_message_after_latest_human(result, "submit_job_record")
    if message is None:
        return None
    content = message.content
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return None
    if not isinstance(content, dict) or not content.get("ok"):
        return None
    record = content.get("record")
    return record if isinstance(record, dict) else content


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


def _run_source_from_trigger(trigger: dict[str, Any]) -> JobRunSource:
    source = trigger.get("source")
    if source == "time":
        return JobRunSource.TIME
    if source in {"event", "wot_event"}:
        return JobRunSource.EVENT
    return JobRunSource.MANUAL


def _job_run_status_from_result(result: dict[str, Any]) -> JobRunStatus:
    if result.get("status") == JobRunStatus.WAITING_FOR_INPUT.value:
        return JobRunStatus.WAITING_FOR_INPUT
    if result.get("status") == JobRunStatus.SKIPPED.value:
        return JobRunStatus.SKIPPED
    if result.get("ok"):
        return JobRunStatus.SUCCEEDED
    return JobRunStatus.FAILED


def _job_run_prompt(job: Job) -> str:
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


_executor: JobExecutor | None = None


def get_job_executor() -> JobExecutor:
    global _executor
    if _executor is None:
        settings = Settings()
        _executor = JobExecutor(settings)
    return _executor


async def close_job_executor() -> None:
    global _executor
    if _executor is not None:
        await _executor.close()
        _executor = None
