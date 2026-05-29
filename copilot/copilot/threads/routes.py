"""FastAPI routes for chat thread metadata and history."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder

from copilot.core.agui_messages import strip_none_fields
from copilot.threads.store import (
    create_thread,
    delete_thread as delete_thread_metadata,
    get_thread,
    list_threads,
    update_thread_title,
)


def create_threads_router(
    *,
    get_settings: Callable[[], Any | None],
    get_checkpointer: Callable[[], Any | None],
    verify_internal_api_key: Callable[[Request], None],
) -> APIRouter:
    router = APIRouter(prefix="/threads", tags=["threads"])

    async def read_optional_json(request: Request) -> dict[str, Any]:
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

    def agent_state_db_path() -> str:
        settings = get_settings()
        if settings is None:
            raise HTTPException(status_code=503, detail="Settings not loaded")
        return settings.agent_state_db_path

    async def count_thread_rows(db_path: str, thread_id: str) -> tuple[int, int]:
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

    async def delete_thread_rows(db_path: str, thread_id: str) -> tuple[int, int]:
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

    async def get_thread_messages_payload(thread_id: str) -> list[dict[str, Any]]:
        checkpointer = get_checkpointer()
        if checkpointer is None:
            raise HTTPException(status_code=503, detail="Checkpointer not ready")

        state = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
        if state is None or state.checkpoint is None:
            return []

        from ag_ui_langgraph.utils import langchain_messages_to_agui  # type: ignore[import-untyped]

        channel_values = state.checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", [])
        if not isinstance(messages, list):
            return []

        agui_messages = jsonable_encoder(langchain_messages_to_agui(messages))
        return strip_none_fields(agui_messages)

    @router.get("")
    async def get_threads(request: Request):
        verify_internal_api_key(request)
        return await asyncio.to_thread(list_threads, agent_state_db_path())

    @router.post("")
    async def post_thread(request: Request):
        verify_internal_api_key(request)

        body = await read_optional_json(request)
        title = body.get("title")
        thread_id = body.get("id")
        created_at = body.get("createdAt")
        updated_at = body.get("updatedAt")

        return await asyncio.to_thread(
            create_thread,
            agent_state_db_path(),
            thread_id=thread_id if isinstance(thread_id, str) and thread_id else None,
            title=title if isinstance(title, str) else "New Chat",
            created_at=created_at if isinstance(created_at, str) and created_at else None,
            updated_at=updated_at if isinstance(updated_at, str) and updated_at else None,
        )

    @router.patch("/{thread_id}")
    async def patch_thread(thread_id: str, request: Request):
        verify_internal_api_key(request)

        body = await read_optional_json(request)
        title = body.get("title")
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(status_code=400, detail="Title is required")

        try:
            return await asyncio.to_thread(
                update_thread_title,
                agent_state_db_path(),
                thread_id=thread_id,
                title=title,
                force=bool(body.get("force")),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/{thread_id}")
    async def get_thread_by_id(thread_id: str, request: Request):
        verify_internal_api_key(request)

        db_path = agent_state_db_path()
        record = await asyncio.to_thread(get_thread, db_path, thread_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Thread not found")

        messages = await get_thread_messages_payload(thread_id)
        return {**record, "messages": messages}

    @router.delete("/{thread_id}")
    async def delete_thread(thread_id: str, request: Request):
        verify_internal_api_key(request)

        db_path = agent_state_db_path()
        deleted_writes, deleted_checkpoints = await count_thread_rows(db_path, thread_id)

        checkpointer = get_checkpointer()
        if checkpointer is not None:
            await checkpointer.adelete_thread(thread_id)
        else:
            deleted_writes, deleted_checkpoints = await delete_thread_rows(db_path, thread_id)
        await asyncio.to_thread(delete_thread_metadata, db_path, thread_id)

        return {
            "ok": True,
            "thread_id": thread_id,
            "deleted_writes": deleted_writes,
            "deleted_checkpoints": deleted_checkpoints,
        }

    return router
