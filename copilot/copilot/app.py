"""FastAPI + AG-UI entrypoint for the Smart Living Copilot."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from ag_ui_langgraph import add_langgraph_fastapi_endpoint  # type: ignore[import-untyped]
from copilotkit import LangGraphAGUIAgent
from fastapi import FastAPI, HTTPException, Request
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel, Field

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:  # pragma: no cover - exercised when optional dep is absent locally.
    AsyncPostgresSaver = None  # type: ignore[assignment]

from copilot.core.llm import _make_llm
from copilot.core.config import get_settings as get_registry_settings
from copilot.core.database import get_connection_pool, init_db, psycopg_conninfo
from copilot.core.health import router as registry_health_router
from copilot.core.lifecycle import shutdown_backend_runtime, start_backend_runtime
from copilot.graph import build_graph
from copilot.graph.checkpointer import CachingCheckpointSaver
from copilot.media import (
    create_media_stream,
    SemanticTextChunker,
    speech_pipelines,
)
from copilot.media.routes import create_media_router
from copilot.core.settings import Settings as AgentSettings
from copilot.threads import (
    init_thread_store,
    suggest_thread_title,
    sync_thread_after_run,
)
from copilot.threads.routes import create_threads_router
from copilot.graph.tools import LOCAL_TOOLS, REGISTRY_TOOLS
from copilot.api_keys.router import router as api_keys_router
from copilot.auth.router import router as me_router
from copilot.jobs import JobService, router as jobs_router
from copilot.wot_runtime.router import router as wot_operations_router
from copilot.search.router import router as search_router
from copilot.things.router import router as things_router

logger = logging.getLogger(__name__)
EMBED_EPHEMERAL_THREAD_PREFIX = "embed-ephemeral-"
NOISY_MEDIA_LOGGERS = (
    "aiortc",
    "aioice",
    "fastrtc",
)

# Module-level references kept alive for the process lifetime.
_agent: LangGraphAGUIAgent | None = None
_graph: Any | None = None
_checkpointer: CachingCheckpointSaver | None = None
_settings: AgentSettings | None = None
_job_service: JobService | None = None
_thread_run_locks: dict[str, asyncio.Lock] = {}
_thread_run_locks_guard = asyncio.Lock()


class JobDispatchRequest(BaseModel):
    thread_id: str
    prompt: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def _is_embed_ephemeral_thread(thread_id: str | None) -> bool:
    return isinstance(thread_id, str) and thread_id.startswith(EMBED_EPHEMERAL_THREAD_PREFIX)


def _quiet_noisy_media_loggers() -> None:
    for logger_name in NOISY_MEDIA_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _checkpoint_database_url(
    *,
    settings: AgentSettings,
    registry_database_url: str,
) -> str:
    if settings.agent_state_database_url:
        return settings.agent_state_database_url

    return registry_database_url


@asynccontextmanager
async def _checkpoint_saver_context(
    *,
    settings: AgentSettings,
    registry_database_url: str,
):
    database_url = _checkpoint_database_url(
        settings=settings,
        registry_database_url=registry_database_url,
    )
    if AsyncPostgresSaver is None:
        raise RuntimeError(
            "Postgres checkpointing requires langgraph-checkpoint-postgres to be installed"
        )

    async with AsyncPostgresSaver.from_conn_string(psycopg_conninfo(database_url)) as postgres_saver:
        await postgres_saver.setup()
        yield postgres_saver


def _log_background_task_exception(
    task: asyncio.Task[None],
    *,
    error_message: str,
) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        logger.warning("%s: task was cancelled", error_message)
    except Exception as exc:
        logger.error("%s: %s", error_message, exc, exc_info=exc)


async def _run_persistence_operation(
    operation: Any,
    *,
    error_message: str,
) -> bool:
    """Run persistence work so cancellation doesn't kill the inner task.

    Returns ``True`` when the caller was cancelled while the operation kept
    running in the background.
    """

    task = asyncio.create_task(operation)
    try:
        await asyncio.shield(task)
        return False
    except asyncio.CancelledError:
        task.add_done_callback(
            lambda finished_task: _log_background_task_exception(
                finished_task,
                error_message=error_message,
            )
        )
        return True
    except Exception:
        logger.exception(error_message)
        return False


async def _finalize_thread_run(thread_id: str | None) -> None:
    if _is_embed_ephemeral_thread(thread_id):
        return

    cancelled = False

    if _checkpointer is not None:
        cancelled = (
            await _run_persistence_operation(
                _checkpointer.flush(thread_id=thread_id),
                error_message=f"Failed to flush checkpoints for {thread_id}",
            )
            or cancelled
        )

    cancelled = (
        await _run_persistence_operation(
            _sync_thread_metadata_after_run(thread_id),
            error_message=f"Failed to sync thread metadata for {thread_id}",
        )
        or cancelled
    )

    if cancelled:
        raise asyncio.CancelledError


async def _thread_run_lock(thread_id: str) -> asyncio.Lock:
    async with _thread_run_locks_guard:
        lock = _thread_run_locks.get(thread_id)
        if lock is None:
            lock = asyncio.Lock()
            _thread_run_locks[thread_id] = lock
        return lock


async def _flush_pending_checkpoints_on_shutdown() -> None:
    if _checkpointer is None:
        return

    for thread_id in await _checkpointer.pending_thread_ids():
        if thread_id is not None and _is_embed_ephemeral_thread(thread_id):
            await _checkpointer.adelete_thread(thread_id)

    cancelled = await _run_persistence_operation(
        _checkpointer.flush(),
        error_message="Failed to flush pending checkpoints during shutdown",
    )

    if cancelled:
        raise asyncio.CancelledError


class _AGUIAgentProxy:
    name = "copilot"

    def clone(self):
        return _AGUIAgentProxy()

    async def run(self, input_data):
        if _agent is None:
            raise RuntimeError("AG-UI agent is not ready")

        thread_id = _request_thread_id(input_data)
        if thread_id:
            lock = await _thread_run_lock(thread_id)
            async with lock:
                try:
                    async for event in _agent.run(input_data):
                        yield event
                finally:
                    await _finalize_thread_run(thread_id)
            return

        try:
            async for event in _agent.run(input_data):
                yield event
        finally:
            await _finalize_thread_run(thread_id)


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
    text_parts = []
    for item in content:
        if isinstance(item, str):
            text_parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            text_parts.append(item["text"])
    return "".join(text_parts)


def _voice_stream_text_from_event(event: Any) -> str:
    if not isinstance(event, tuple) or len(event) != 2:
        return ""
    message, metadata = event
    if not isinstance(message, AIMessageChunk) or not isinstance(metadata, dict):
        return ""
    if metadata.get("langgraph_node") not in {"respond", "control_llm", "analysis_llm"}:
        return ""
    if getattr(message, "tool_call_chunks", None):
        return ""
    return _text_from_message_content(message.content)


async def _submit_voice_transcript_to_chat(thread_id: str, transcript: str) -> str:
    if _graph is None:
        raise RuntimeError("LangGraph is not ready")

    lock = await _thread_run_lock(thread_id)
    async with lock:
        try:
            result = await _graph.ainvoke(
                {"messages": [HumanMessage(content=transcript)]},
                config={"configurable": {"thread_id": thread_id}},
            )
            return _assistant_text_from_graph_result(result)
        finally:
            await _finalize_thread_run(thread_id)


async def _stream_voice_transcript_to_chat(
    thread_id: str,
    transcript: str,
) -> AsyncIterator[str]:
    if _graph is None:
        raise RuntimeError("LangGraph is not ready")

    chunker = SemanticTextChunker()
    lock = await _thread_run_lock(thread_id)
    async with lock:
        try:
            async for event in _graph.astream(
                {"messages": [HumanMessage(content=transcript)]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode="messages",
            ):
                text = _voice_stream_text_from_event(event)
                if not text:
                    continue
                for chunk in chunker.accept(text):
                    yield chunk
            final_chunk = chunker.flush()
            if final_chunk:
                yield final_chunk
        finally:
            await _finalize_thread_run(thread_id)


async def dispatch_prompt_to_graph(
    thread_id: str,
    prompt: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a prompt through the graph for one thread and return the assistant text.

    Shared by the ``/internal/jobs/dispatch`` endpoint and the in-process job
    runner, so both reach the agent the same way.
    """
    if _graph is None:
        raise RuntimeError("Graph is not ready")

    result = await _graph.ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config={"configurable": {"thread_id": thread_id}},
    )

    assistant_text = ""
    for message in reversed(result.get("messages", [])):
        if isinstance(message, AIMessage):
            content = message.content
            assistant_text = content if isinstance(content, str) else str(content)
            break

    return {
        "ok": True,
        "thread_id": thread_id,
        "assistant": assistant_text,
        "metadata": metadata or {},
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent, _graph, _checkpointer, _settings, _job_service

    settings = AgentSettings()
    _settings = settings
    logging.basicConfig(level=settings.log_level)
    _quiet_noisy_media_loggers()
    await asyncio.to_thread(init_db)
    await asyncio.to_thread(init_thread_store)

    registry_settings = get_registry_settings()
    connection_pool = get_connection_pool()
    await start_backend_runtime(
        app,
        settings=registry_settings,
        connection_pool=connection_pool,
    )

    try:
        llm = _make_llm(settings)

        async with _checkpoint_saver_context(
            settings=settings,
            registry_database_url=registry_settings.DATABASE_URL,
        ) as saver:
            _checkpointer = CachingCheckpointSaver(saver)
            checkpointer = _checkpointer
            graph = build_graph(
                llm=llm,
                registry_tools=REGISTRY_TOOLS,
                local_tools=LOCAL_TOOLS,
                max_tokens=settings.max_context_tokens,
                checkpointer=checkpointer,
                parallel_tool_calls=settings.parallel_tool_calls,
                max_checkpoint_tokens=settings.max_checkpoint_tokens,
                vision_enabled=settings.vision_enabled,
            )
            graph = graph.with_config(recursion_limit=settings.recursion_limit)
            _graph = graph
            speech_pipelines.configure(
                settings,
                _submit_voice_transcript_to_chat,
                _stream_voice_transcript_to_chat,
            )

            logger.info(
                "Graph created with %d registry tools, model=%s, recursion_limit=%d",
                len(REGISTRY_TOOLS),
                settings.openai_model,
                settings.recursion_limit,
            )

            _agent = LangGraphAGUIAgent(
                name="copilot",
                description="Smart Living Copilot",
                graph=graph,
            )
            _graph = graph

            app.state.settings = settings
            app.state.agent_settings = settings
            if settings.jobs_enabled:
                _job_service = JobService(settings, dispatch_prompt=dispatch_prompt_to_graph)
                await _job_service.start()
                app.state.service = _job_service
                logger.info("Job runner started (in-process)")
            else:
                logger.info("Job runner disabled (JOBS_ENABLED=false)")

            yield
            if _job_service is not None:
                await _job_service.stop()
            await speech_pipelines.stop_all()
            await _flush_pending_checkpoints_on_shutdown()
    finally:
        await shutdown_backend_runtime(app)


app = FastAPI(title="Smart Living Copilot", lifespan=lifespan)
add_langgraph_fastapi_endpoint(app=app, agent=_AGUIAgentProxy(), path="/ag-ui")
app.include_router(registry_health_router)
app.include_router(me_router)
app.include_router(search_router)
app.include_router(things_router)
app.include_router(api_keys_router)
app.include_router(wot_operations_router)
app.include_router(jobs_router)
_media_stream = create_media_stream()


def _verify_internal_api_key(request: Request) -> None:
    if not _settings or not _settings.internal_api_key:
        return

    auth_header = request.headers.get("authorization", "")
    expected = f"Bearer {_settings.internal_api_key}"
    if auth_header != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


def _current_settings() -> AgentSettings | None:
    return _settings


def _current_checkpointer() -> CachingCheckpointSaver | None:
    return _checkpointer


def _request_thread_id(input_data: Any) -> str | None:
    if isinstance(input_data, dict):
        for key in ("threadId", "thread_id"):
            value = input_data.get(key)
            if isinstance(value, str) and value:
                return value

        configurable = input_data.get("configurable")
        if isinstance(configurable, dict):
            for key in ("threadId", "thread_id"):
                value = configurable.get(key)
                if isinstance(value, str) and value:
                    return value
        return None

    for attr in ("threadId", "thread_id"):
        value = getattr(input_data, attr, None)
        if isinstance(value, str) and value:
            return value

    configurable = getattr(input_data, "configurable", None)
    if isinstance(configurable, dict):
        for key in ("threadId", "thread_id"):
            value = configurable.get(key)
            if isinstance(value, str) and value:
                return value

    return None


@app.post("/internal/jobs/dispatch")
async def dispatch_job_prompt(payload: JobDispatchRequest, request: Request):
    _verify_internal_api_key(request)
    try:
        return await dispatch_prompt_to_graph(
            payload.thread_id,
            payload.prompt,
            payload.metadata,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def _sync_thread_metadata_after_run(thread_id: str | None) -> None:
    if not thread_id or _settings is None:
        return

    if _checkpointer is not None and await _checkpointer.is_deleted_thread(thread_id):
        return

    title = await _suggest_thread_title(thread_id)
    await asyncio.to_thread(
        sync_thread_after_run,
        thread_id,
        suggested_title=title,
    )


async def _suggest_thread_title(thread_id: str) -> str | None:
    if _checkpointer is None:
        return None

    state = await _checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
    if state is None or state.checkpoint is None:
        return None

    channel_values = state.checkpoint.get("channel_values", {})
    messages = channel_values.get("messages", [])
    if not isinstance(messages, list):
        return None

    return suggest_thread_title(messages)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(
    create_media_router(
        get_settings=_current_settings,
        verify_internal_api_key=_verify_internal_api_key,
    )
)
app.include_router(
    create_threads_router(
        get_checkpointer=_current_checkpointer,
        verify_internal_api_key=_verify_internal_api_key,
    )
)

if _media_stream is not None:
    # Keep explicit /media routes above the mounted FastRTC app; Starlette
    # matches routes in registration order.
    _media_stream.mount(app, path="/media", tags=["media"])
