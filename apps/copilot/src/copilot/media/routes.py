"""FastAPI routes for LiveKit media sessions."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from copilot.media.livekit import (
    LiveKitAgentDispatchError,
    create_livekit_connection_details,
    dispatch_livekit_agent,
    is_livekit_configured,
)


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


def _body_string(body: dict[str, Any], *names: str, default: str = "") -> str:
    for name in names:
        value = body.get(name)
        if isinstance(value, str) and value:
            return value
    return default


async def _create_livekit_token_response(settings: Any, request: Request) -> dict[str, Any]:
    if not is_livekit_configured(settings):
        return {"enabled": False}

    body = await _read_optional_json(request)
    thread_id = _body_string(body, "threadId", "thread_id") or None
    try:
        details = create_livekit_connection_details(settings, thread_id=thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return details.as_response()


async def _dispatch_livekit_agent_response(settings: Any, request: Request) -> dict[str, Any]:
    if not is_livekit_configured(settings):
        return {"enabled": False}

    body = await _read_optional_json(request)
    try:
        await dispatch_livekit_agent(
            settings,
            room=_body_string(body, "room"),
            thread_id=_body_string(body, "threadId", "thread_id") or None,
            participant_identity=_body_string(
                body,
                "participantIdentity",
                "participant_identity",
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LiveKitAgentDispatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"enabled": True, "dispatched": True}


def create_media_router(
    *,
    get_settings: Callable[[], Any | None],
    verify_internal_api_key: Callable[[Request], None],
) -> APIRouter:
    router = APIRouter(prefix="/media", tags=["media"])

    @router.post("/livekit/token")
    async def create_livekit_token(request: Request):
        verify_internal_api_key(request)
        return await _create_livekit_token_response(get_settings(), request)

    @router.post("/livekit/dispatch")
    async def dispatch_livekit_agent_to_room(request: Request):
        verify_internal_api_key(request)
        return await _dispatch_livekit_agent_response(get_settings(), request)

    return router
