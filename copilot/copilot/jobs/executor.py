from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from copilot.agent import build_graph
from copilot.agent.tools.get_current_time import get_current_time
from copilot.agent.tools.look_at_camera import look_at_camera
from copilot.agent.tools.run_code import run_code
from copilot.agent.tools.wot_registry import REGISTRY_TOOLS
from copilot.core.config import get_settings as get_registry_settings
from copilot.core.database import init_db
from copilot.core.llm import make_llm
from copilot.core.settings import Settings
from copilot.jobs.code_executor_client import CodeExecutorClient
from copilot.jobs.models import Job
from copilot.jobs.results import JobRunEventPublisher
from copilot.jobs.store import JobStore, utc_now
from copilot.search import ThingSearchService, set_active_search_service

logger = logging.getLogger(__name__)


class BackgroundAgentRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graph: Any | None = None
        self._search_service: ThingSearchService | None = None

    async def close(self) -> None:
        set_active_search_service(None)
        if self._search_service is not None:
            await self._search_service.close()
            self._search_service = None
        self._graph = None

    def _ensure_graph(self) -> Any:
        if self._graph is not None:
            return self._graph

        init_db()
        registry_settings = get_registry_settings()
        self._search_service = ThingSearchService(registry_settings)
        set_active_search_service(self._search_service)

        llm = make_llm(self._settings)
        graph = build_graph(
            llm=llm,
            registry_tools=REGISTRY_TOOLS,
            local_tools=[run_code, get_current_time, look_at_camera],
            max_tokens=self._settings.max_context_tokens,
            checkpointer=None,
            parallel_tool_calls=self._settings.parallel_tool_calls,
            vision_enabled=self._settings.vision_enabled,
        )
        self._graph = graph.with_config(recursion_limit=self._settings.recursion_limit)
        return self._graph

    async def run(self, job: Job, *, trigger: dict[str, Any]) -> dict[str, Any]:
        graph = self._ensure_graph()
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=job.prompt or "")]},
            config={"configurable": {"thread_id": f"job:{job.id}"}},
        )
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

    async def run_job(self, job_id: str, trigger: dict[str, Any]) -> dict[str, Any]:
        job = await self._repo.get_job(job_id)
        if job.job_type == "analysis":
            result = await self._run_analysis_job(job, trigger=trigger)
        else:
            result = await self._run_prompt_job(job, trigger=trigger)

        await self._repo.record_job_result(
            job_id=job.id,
            now=utc_now(),
            success=bool(result.get("ok")),
            error=result.get("error"),
            response_text=result.get("assistant"),
            last_fetch_value=result.get("last_fetch_value"),
        )
        # A one-shot time job has fired its only run; disable it so startup
        # reconciliation does not re-create a schedule for it. The Redis schedule
        # itself is removed automatically by the source's post_send.
        if trigger.get("source") == "time" and job.interval_seconds is None:
            await self._repo.disable_job(job.id)
        await self._event_publisher.publish_job_run(job.id)
        return result

    async def _run_prompt_job(self, job: Job, *, trigger: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self._agent_runner.run(job, trigger=trigger)
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
            last_fetch_value = _extract_last_fetch_value(response)

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
                "last_fetch_value": last_fetch_value,
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


def _extract_last_fetch_value(response: dict[str, Any]) -> str | None:
    stdout = str(response.get("stdout", "") or "").strip()
    if not stdout:
        return None

    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None

    last_line = lines[-1]
    marker = "WOT_LAST_VALUE="
    if last_line.startswith(marker):
        return last_line[len(marker) :][:500]

    try:
        payload = json.loads(last_line)
        if isinstance(payload, dict):
            for key in ("last_fetch_value", "last_value", "value", "wot_value"):
                if key in payload:
                    return str(payload[key])[:500]
    except Exception:
        pass

    return last_line[:500]


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
