"""FastAPI routes for chat thread metadata and history."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from copilot.threads.messages import checkpoint_thread_messages
from copilot.threads.models import (
    DEFAULT_THREAD_TITLE,
    CreateThreadRequest,
    UpdateThreadTitleRequest,
)
from copilot.threads.store import (
    create_thread,
    get_thread,
    list_threads,
    update_thread_title,
)
from copilot.threads.store import (
    delete_thread as delete_thread_metadata,
)


async def _get_thread_messages_payload(
    *,
    get_checkpointer: Callable[[], Any | None],
    thread_id: str,
) -> list[dict[str, Any]]:
    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise HTTPException(status_code=503, detail="Checkpointer not ready")

    return await checkpoint_thread_messages(checkpointer, thread_id)


async def _create_thread_record(body: CreateThreadRequest | None) -> dict[str, Any]:
    payload = body or CreateThreadRequest()
    return await asyncio.to_thread(
        create_thread,
        thread_id=payload.id,
        title=payload.title or DEFAULT_THREAD_TITLE,
        created_at=payload.created_at,
        updated_at=payload.updated_at,
    )


async def _update_thread_record(
    *,
    thread_id: str,
    body: UpdateThreadTitleRequest,
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            update_thread_title,
            thread_id=thread_id,
            title=body.title,
            force=body.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _thread_record_with_messages(
    *,
    get_checkpointer: Callable[[], Any | None],
    thread_id: str,
) -> dict[str, Any]:
    record = await asyncio.to_thread(get_thread, thread_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = await _get_thread_messages_payload(
        get_checkpointer=get_checkpointer,
        thread_id=thread_id,
    )
    return {**record, "messages": messages}


async def _delete_thread_record(
    *,
    get_checkpointer: Callable[[], Any | None],
    thread_id: str,
) -> dict[str, Any]:
    checkpointer = get_checkpointer()
    if checkpointer is not None:
        await checkpointer.adelete_thread(thread_id)

    deleted = await asyncio.to_thread(delete_thread_metadata, thread_id)

    return {
        "ok": True,
        "thread_id": thread_id,
        "deleted": deleted,
    }


def create_threads_router(
    *,
    get_checkpointer: Callable[[], Any | None],
    verify_internal_api_key: Callable[[Request], None],
) -> APIRouter:
    router = APIRouter(prefix="/threads", tags=["threads"])

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

        return await _create_thread_record(body)

    @router.patch("/{thread_id}")
    async def patch_thread(
        thread_id: str,
        request: Request,
        body: UpdateThreadTitleRequest,
    ):
        verify_internal_api_key(request)

        return await _update_thread_record(thread_id=thread_id, body=body)

    @router.get("/{thread_id}")
    async def get_thread_by_id(thread_id: str, request: Request):
        verify_internal_api_key(request)

        return await _thread_record_with_messages(
            get_checkpointer=get_checkpointer,
            thread_id=thread_id,
        )

    @router.delete("/{thread_id}")
    async def delete_thread(thread_id: str, request: Request):
        verify_internal_api_key(request)

        return await _delete_thread_record(
            get_checkpointer=get_checkpointer,
            thread_id=thread_id,
        )

    return router
