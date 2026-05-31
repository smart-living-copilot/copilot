"""FastAPI routes for chat thread metadata and history."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from copilot.threads.messages import checkpoint_thread_messages
from copilot.threads.models import (
    CreateThreadRequest,
    DEFAULT_THREAD_TITLE,
    UpdateThreadTitleRequest,
)
from copilot.threads.store import (
    create_thread,
    delete_thread as delete_thread_metadata,
    get_thread,
    list_threads,
    update_thread_title,
)


def create_threads_router(
    *,
    get_checkpointer: Callable[[], Any | None],
    verify_internal_api_key: Callable[[Request], None],
) -> APIRouter:
    router = APIRouter(prefix="/threads", tags=["threads"])

    async def get_thread_messages_payload(thread_id: str) -> list[dict[str, Any]]:
        checkpointer = get_checkpointer()
        if checkpointer is None:
            raise HTTPException(status_code=503, detail="Checkpointer not ready")

        return await checkpoint_thread_messages(checkpointer, thread_id)

    @router.get("")
    async def get_threads(request: Request):
        verify_internal_api_key(request)
        return await asyncio.to_thread(list_threads)

    @router.post("")
    async def post_thread(
        request: Request,
        body: CreateThreadRequest | None = Body(default=None),
    ):
        verify_internal_api_key(request)

        payload = body or CreateThreadRequest()

        return await asyncio.to_thread(
            create_thread,
            thread_id=payload.id,
            title=payload.title or DEFAULT_THREAD_TITLE,
            created_at=payload.created_at,
            updated_at=payload.updated_at,
        )

    @router.patch("/{thread_id}")
    async def patch_thread(
        thread_id: str,
        request: Request,
        body: UpdateThreadTitleRequest,
    ):
        verify_internal_api_key(request)

        try:
            return await asyncio.to_thread(
                update_thread_title,
                thread_id=thread_id,
                title=body.title,
                force=body.force,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/{thread_id}")
    async def get_thread_by_id(thread_id: str, request: Request):
        verify_internal_api_key(request)

        record = await asyncio.to_thread(get_thread, thread_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Thread not found")

        messages = await get_thread_messages_payload(thread_id)
        return {**record, "messages": messages}

    @router.delete("/{thread_id}")
    async def delete_thread(thread_id: str, request: Request):
        verify_internal_api_key(request)

        checkpointer = get_checkpointer()
        if checkpointer is not None:
            await checkpointer.adelete_thread(thread_id)

        deleted = await asyncio.to_thread(delete_thread_metadata, thread_id)

        return {
            "ok": True,
            "thread_id": thread_id,
            "deleted": deleted,
        }

    return router
