"""FastAPI + AG-UI entrypoint for the Smart Living Copilot."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite
from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from fastapi import FastAPI, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage
from fastapi.encoders import jsonable_encoder
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel, Field

from copilot.agent import _load_mcp_tools, _make_llm, _make_mcp_client
from copilot.agui_messages import strip_none_fields
from copilot.graph import build_graph
from copilot.graph.checkpointer import CachingCheckpointSaver
from copilot.media import (
    create_media_stream,
    media_sessions,
    parse_rtc_configuration,
    speech_pipelines,
)
from copilot.models import Settings
from copilot.speech import SemanticTextChunker
from copilot.thread_store import (
    create_thread,
    delete_thread as delete_thread_metadata,
    get_thread,
    init_thread_store,
    list_threads,
    sync_thread_after_run,
    update_thread_title,
)
from copilot.thread_titles import suggest_thread_title
from copilot.tools import AVAILABLE_TOOLS
from copilot.jobs import JobService, router as jobs_router

logger = logging.getLogger(__name__)
EMBED_EPHEMERAL_THREAD_PREFIX = "embed-ephemeral-"
NOISY_MEDIA_LOGGERS = (
    "aiortc",
    "aioice",
    "fastrtc",
)

# Module-level references kept alive for the process lifetime.
_mcp_client = None
_agent: LangGraphAGUIAgent | None = None
_graph: Any | None = None
_checkpointer: CachingCheckpointSaver | None = None
_settings: Settings | None = None
_job_service: JobService | None = None
_thread_run_locks: dict[str, asyncio.Lock] = {}
_thread_run_locks_guard = asyncio.Lock()
_graph: Any | None = None


class JobDispatchRequest(BaseModel):
    thread_id: str
    prompt: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def _is_embed_ephemeral_thread(thread_id: str | None) -> bool:
    return isinstance(thread_id, str) and thread_id.startswith(EMBED_EPHEMERAL_THREAD_PREFIX)


def _quiet_noisy_media_loggers() -> None:
    for logger_name in NOISY_MEDIA_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


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
        if _is_embed_ephemeral_thread(thread_id):
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
    global _mcp_client, _agent, _graph, _checkpointer, _settings, _job_service

    settings = Settings()
    _settings = settings
    logging.basicConfig(level=settings.log_level)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    _quiet_noisy_media_loggers()
    await asyncio.to_thread(init_thread_store, settings.agent_state_db_path)

    llm = _make_llm(settings)

    _mcp_client = _make_mcp_client(settings)
    mcp_tools = await _load_mcp_tools(_mcp_client)

    async with AsyncSqliteSaver.from_conn_string(settings.agent_state_db_path) as sqlite_saver:
        _checkpointer = CachingCheckpointSaver(sqlite_saver)
        checkpointer = _checkpointer
        graph = build_graph(
            llm=llm,
            mcp_tools=mcp_tools,
            local_tools=AVAILABLE_TOOLS,
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
            "Graph created with %d MCP tools, model=%s, recursion_limit=%d",
            len(mcp_tools),
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


app = FastAPI(title="Smart Living Copilot", lifespan=lifespan)
add_langgraph_fastapi_endpoint(app=app, agent=_AGUIAgentProxy(), path="/ag-ui")
app.include_router(jobs_router)
_media_stream = create_media_stream()


def _verify_internal_api_key(request: Request) -> None:
    if not _settings or not _settings.internal_api_key:
        return

    auth_header = request.headers.get("authorization", "")
    expected = f"Bearer {_settings.internal_api_key}"
    if auth_header != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


@app.middleware("http")
async def _verify_media_http_requests(request: Request, call_next):
    if request.url.path.startswith("/media/"):
        try:
            _verify_internal_api_key(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


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


async def _read_optional_json(request: Request) -> dict[str, Any]:
    raw_body = await request.body()
    if not raw_body:
        return {}

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="JSON object body is required")

    return parsed


async def _count_thread_rows(db_path: str, thread_id: str) -> tuple[int, int]:
    async with aiosqlite.connect(db_path) as db:
        writes_cursor = await db.execute(
            "SELECT COUNT(*) FROM writes WHERE thread_id = ?",
            (thread_id,),
        )
        writes_row = await writes_cursor.fetchone()
        checkpoints_cursor = await db.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?",
            (thread_id,),
        )
        checkpoints_row = await checkpoints_cursor.fetchone()

    return (
        int(writes_row[0]) if writes_row else 0,
        int(checkpoints_row[0]) if checkpoints_row else 0,
    )


async def _delete_thread_rows(db_path: str, thread_id: str) -> tuple[int, int]:
    async with aiosqlite.connect(db_path) as db:
        writes_cursor = await db.execute(
            "DELETE FROM writes WHERE thread_id = ?",
            (thread_id,),
        )
        checkpoints_cursor = await db.execute(
            "DELETE FROM checkpoints WHERE thread_id = ?",
            (thread_id,),
        )
        await db.commit()

    return writes_cursor.rowcount, checkpoints_cursor.rowcount


async def _sync_thread_metadata_after_run(thread_id: str | None) -> None:
    if not thread_id or _settings is None:
        return

    if _checkpointer is not None and await _checkpointer.is_deleted_thread(thread_id):
        return

    title = await _suggest_thread_title(thread_id)
    await asyncio.to_thread(
        sync_thread_after_run,
        _settings.agent_state_db_path,
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


async def _get_thread_messages_payload(thread_id: str) -> list[dict[str, Any]]:
    if _checkpointer is None:
        raise HTTPException(status_code=503, detail="Checkpointer not ready")

    state = await _checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
    if state is None or state.checkpoint is None:
        return []

    from ag_ui_langgraph.utils import langchain_messages_to_agui

    channel_values = state.checkpoint.get("channel_values", {})
    messages = channel_values.get("messages", [])
    if not isinstance(messages, list):
        return []

    agui_messages = jsonable_encoder(langchain_messages_to_agui(messages))
    return strip_none_fields(agui_messages)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/media/rtc-configuration")
async def get_media_rtc_configuration(request: Request):
    _verify_internal_api_key(request)

    try:
        raw_configuration = _settings.media_rtc_configuration if _settings else ""
        configuration = parse_rtc_configuration(raw_configuration)
        configuration["iceGatherTimeoutMs"] = (
            _settings.media_ice_gather_timeout_ms if _settings else 750
        )
        return configuration
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/media/sessions")
async def get_media_sessions(request: Request):
    _verify_internal_api_key(request)
    return {"sessions": media_sessions.snapshots()}


@app.get("/media/sessions/{webrtc_id}")
async def get_media_session(webrtc_id: str, request: Request):
    _verify_internal_api_key(request)
    stats = media_sessions.get(webrtc_id)
    if stats is None:
        raise HTTPException(status_code=404, detail="Media session not found")
    return stats


@app.get("/media/sessions/{webrtc_id}/stream")
async def stream_media_session(webrtc_id: str, request: Request):
    _verify_internal_api_key(request)

    async def event_generator():
        previous: tuple[str | None, str | None, bool] | None = None
        idle_ticks = 0
        missing_ticks = 0
        while True:
            if await request.is_disconnected():
                return
            current = media_sessions.latest_text_fields(webrtc_id)
            if current is None:
                # Tolerate a brief gap (e.g. client connects before the
                # offer round-trip has registered the session) but give up
                # once the session looks truly gone.
                missing_ticks += 1
                if missing_ticks >= 75:
                    yield "event: end\ndata: {}\n\n"
                    return
                await asyncio.sleep(0.2)
                continue
            missing_ticks = 0
            latest_transcript_text, latest_assistant_text, assistant_response_pending = current
            if current != previous:
                previous = current
                payload = json.dumps(
                    {
                        "latest_transcript_text": latest_transcript_text,
                        "latest_assistant_text": latest_assistant_text,
                        "assistant_response_pending": assistant_response_pending,
                    }
                )
                yield f"event: snapshot\ndata: {payload}\n\n"
                idle_ticks = 0
            else:
                idle_ticks += 1
                # Keep proxies and load balancers from closing the connection on idle
                if idle_ticks >= 75:
                    yield ": keepalive\n\n"
                    idle_ticks = 0
            await asyncio.sleep(0.2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/media/sessions/{webrtc_id}/metadata")
async def set_media_session_metadata(webrtc_id: str, request: Request):
    _verify_internal_api_key(request)
    body = await _read_optional_json(request)
    thread_id = body.get("threadId")
    stats = media_sessions.set_metadata(
        webrtc_id,
        thread_id=thread_id if isinstance(thread_id, str) and thread_id else None,
    )
    return jsonable_encoder(stats)


@app.delete("/media/sessions/{webrtc_id}")
async def delete_media_session(webrtc_id: str, request: Request):
    _verify_internal_api_key(request)
    await speech_pipelines.stop(webrtc_id)
    return {"ok": media_sessions.remove(webrtc_id)}


if _media_stream is not None:
    # Keep explicit /media routes above the mounted FastRTC app; Starlette
    # matches routes in registration order.
    _media_stream.mount(app, path="/media", tags=["media"])


@app.get("/threads")
async def get_threads(request: Request):
    _verify_internal_api_key(request)

    if _settings is None:
        raise HTTPException(status_code=503, detail="Settings not loaded")

    return await asyncio.to_thread(list_threads, _settings.agent_state_db_path)


@app.post("/threads")
async def post_thread(request: Request):
    _verify_internal_api_key(request)

    if _settings is None:
        raise HTTPException(status_code=503, detail="Settings not loaded")

    body = await _read_optional_json(request)
    title = body.get("title")
    thread_id = body.get("id")
    created_at = body.get("createdAt")
    updated_at = body.get("updatedAt")

    record = await asyncio.to_thread(
        create_thread,
        _settings.agent_state_db_path,
        thread_id=thread_id if isinstance(thread_id, str) and thread_id else None,
        title=title if isinstance(title, str) else "New Chat",
        created_at=created_at if isinstance(created_at, str) and created_at else None,
        updated_at=updated_at if isinstance(updated_at, str) and updated_at else None,
    )
    return record


@app.patch("/threads/{thread_id}")
async def patch_thread(thread_id: str, request: Request):
    _verify_internal_api_key(request)

    if _settings is None:
        raise HTTPException(status_code=503, detail="Settings not loaded")

    body = await _read_optional_json(request)
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    try:
        return await asyncio.to_thread(
            update_thread_title,
            _settings.agent_state_db_path,
            thread_id=thread_id,
            title=title,
            force=bool(body.get("force")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/threads/{thread_id}")
async def get_thread_by_id(thread_id: str, request: Request):
    _verify_internal_api_key(request)

    if _settings is None:
        raise HTTPException(status_code=503, detail="Settings not loaded")

    record = await asyncio.to_thread(get_thread, _settings.agent_state_db_path, thread_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = await _get_thread_messages_payload(thread_id)
    return {**record, "messages": messages}


@app.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, request: Request):
    _verify_internal_api_key(request)

    if _settings is None:
        raise HTTPException(status_code=503, detail="Settings not loaded")

    deleted_writes, deleted_checkpoints = await _count_thread_rows(
        _settings.agent_state_db_path,
        thread_id,
    )

    if _checkpointer is not None:
        await _checkpointer.adelete_thread(thread_id)
    else:
        deleted_writes, deleted_checkpoints = await _delete_thread_rows(
            _settings.agent_state_db_path,
            thread_id,
        )
    await asyncio.to_thread(delete_thread_metadata, _settings.agent_state_db_path, thread_id)

    return {
        "ok": True,
        "thread_id": thread_id,
        "deleted_writes": deleted_writes,
        "deleted_checkpoints": deleted_checkpoints,
    }
