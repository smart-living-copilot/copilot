"""FastAPI + AG-UI entrypoint for the Smart Living Copilot."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite
from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from copilot.agent import _load_mcp_tools, _make_llm, _make_mcp_client
from copilot.agui_messages import strip_none_fields
from copilot.graph import build_graph
from copilot.graph.checkpointer import CachingCheckpointSaver
from copilot.models import Settings
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

logger = logging.getLogger(__name__)
EMBED_EPHEMERAL_THREAD_PREFIX = "embed-ephemeral-"

# Module-level references kept alive for the process lifetime.
_mcp_client = None
_agent: LangGraphAGUIAgent | None = None
_checkpointer: CachingCheckpointSaver | None = None
_settings: Settings | None = None


def _is_embed_ephemeral_thread(thread_id: str | None) -> bool:
    return isinstance(thread_id, str) and thread_id.startswith(EMBED_EPHEMERAL_THREAD_PREFIX)


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
        try:
            async for event in _agent.run(input_data):
                yield event
        finally:
            await _finalize_thread_run(thread_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mcp_client, _agent, _checkpointer, _settings

    settings = Settings()
    _settings = settings
    logging.basicConfig(level=settings.log_level)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
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
        )
        graph = graph.with_config(recursion_limit=settings.recursion_limit)

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

        yield
        await _flush_pending_checkpoints_on_shutdown()


app = FastAPI(title="Smart Living Copilot", lifespan=lifespan)
add_langgraph_fastapi_endpoint(app=app, agent=_AGUIAgentProxy(), path="/ag-ui")


def _verify_internal_api_key(request: Request) -> None:
    if not _settings or not _settings.internal_api_key:
        return

    auth_header = request.headers.get("authorization", "")
    expected = f"Bearer {_settings.internal_api_key}"
    if auth_header != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


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
