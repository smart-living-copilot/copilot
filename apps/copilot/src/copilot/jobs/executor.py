from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:  # pragma: no cover - dependency is installed in the app image.
    AsyncPostgresSaver = None  # type: ignore[assignment]

from copilot.agent import build_graph
from copilot.agent.tools.ask_job_user import ask_job_user
from copilot.agent.tools.get_current_time import get_current_time
from copilot.agent.tools.look_at_camera import look_at_camera
from copilot.agent.tools.run_code import run_code
from copilot.agent.tools.wot_registry import REGISTRY_TOOLS
from copilot.core.config import get_settings as get_registry_settings
from copilot.core.database import init_db, psycopg_conninfo
from copilot.core.llm import make_llm
from copilot.core.settings import Settings
from copilot.clients.code_executor import CodeExecutorClient
from copilot.jobs.models import (
    Job,
    JobActionKind,
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
        graph = build_graph(
            llm=llm,
            registry_tools=REGISTRY_TOOLS,
            local_tools=[run_code, get_current_time, look_at_camera, ask_job_user],
            max_tokens=self._settings.max_context_tokens,
            checkpointer=self._checkpointer,
            parallel_tool_calls=self._settings.parallel_tool_calls,
            vision_enabled=self._settings.vision_enabled,
        )
        self._graph = graph.with_config(recursion_limit=self._settings.recursion_limit)
        return self._graph

    async def run(
        self,
        job: Job,
        *,
        run_id: str,
        trigger: dict[str, Any],
    ) -> dict[str, Any]:
        graph = await self._ensure_graph()
        message = trigger.get("message") if trigger.get("source") == "user_reply" else None
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=message or job.prompt or "")]},
            config={
                "configurable": {
                    "thread_id": job.job_thread_id,
                    "job_id": job.id,
                    "run_id": run_id,
                }
            },
        )
        waiting_question = _waiting_question_from_graph_result(result)
        if waiting_question:
            return {
                "ok": True,
                "status": JobRunStatus.WAITING_FOR_INPUT.value,
                "response": result,
                "assistant": waiting_question,
                "waiting_question": waiting_question,
                "metadata": {"trigger": trigger},
            }
        assistant = _assistant_text_from_graph_result(result)
        if not assistant:
            assistant = json.dumps(result, ensure_ascii=True, default=str)[:2000]
        return {
            "ok": True,
            "response": result,
            "assistant": assistant,
            "metadata": {"trigger": trigger},
        }


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
            run_source = JobRunSource.MANUAL
            run = await self._repo.start_reply_job_run(
                job_id=job_id,
                message=str(trigger.get("message") or ""),
                previous_run_id=trigger.get("previous_run_id"),
                now=now,
            )
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
            result = await self._run_prompt_job(job, run_id=run.id, trigger=trigger)

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
        run_id: str,
        trigger: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return await self._agent_runner.run(job, run_id=run_id, trigger=trigger)
        except Exception as exc:
            logger.error("Failed prompt job %s: %s", job.id, exc, exc_info=exc)
            return {"ok": False, "error": str(exc), "metadata": {"trigger": trigger}}

    async def _run_analysis_job(self, job: Job, *, trigger: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._code_executor_client.execute(
                session_id=f"job-analysis:{job.id}",
                code=job.analysis_code or "",
            )
            stdout = str(response.get("stdout", "")).strip()
            images = response.get("images", [])
            plotly = response.get("plotly", [])

            parts: list[str] = []
            if stdout:
                parts.append(stdout)
            if images:
                parts.append(f"images={len(images)}")
            if plotly:
                parts.append(f"plotly={len(plotly)}")
            if not parts:
                parts.append("(no output)")

            return {
                "ok": True,
                "response": response,
                "assistant": "\n".join(parts)[:4000],
                "metadata": {"trigger": trigger},
            }
        except Exception as exc:
            logger.error("Failed analysis job %s: %s", job.id, exc, exc_info=exc)
            return {"ok": False, "error": str(exc), "metadata": {"trigger": trigger}}


def _assistant_text_from_graph_result(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        return _text_from_message_content(message.content).strip()
    return ""


def _waiting_question_from_graph_result(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    messages = result.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue
        if message.name != "ask_job_user":
            continue
        content = message.content
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return content.strip() or None
        if isinstance(content, dict):
            question = content.get("question")
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


def _run_source_from_trigger(trigger: dict[str, Any]) -> JobRunSource:
    source = trigger.get("source")
    if source == "time":
        return JobRunSource.TIME
    if source in {"event", "wot_event"}:
        return JobRunSource.EVENT
    return JobRunSource.MANUAL


def _job_run_status_from_result(result: dict[str, Any]) -> JobRunStatus:
    if result.get("status") == JobRunStatus.WAITING_FOR_INPUT:
        return JobRunStatus.WAITING_FOR_INPUT
    if result.get("status") == JobRunStatus.SKIPPED:
        return JobRunStatus.SKIPPED
    if result.get("ok"):
        return JobRunStatus.SUCCEEDED
    return JobRunStatus.FAILED


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
