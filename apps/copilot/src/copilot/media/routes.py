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


def create_media_router(
    *,
    get_settings: Callable[[], Any | None],
    verify_internal_api_key: Callable[[Request], None],
) -> APIRouter:
    router = APIRouter(prefix="/media", tags=["media"])

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

    @router.post("/livekit/token")
    async def create_livekit_token(request: Request):
        verify_internal_api_key(request)
        settings = get_settings()
        if not is_livekit_configured(settings):
            return {"enabled": False}

        body = await read_optional_json(request)
        raw_thread_id = body.get("threadId", body.get("thread_id"))
        thread_id = raw_thread_id if isinstance(raw_thread_id, str) and raw_thread_id else None
        try:
            details = create_livekit_connection_details(settings, thread_id=thread_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return details.as_response()

    @router.post("/livekit/dispatch")
    async def dispatch_livekit_agent_to_room(request: Request):
        verify_internal_api_key(request)
        settings = get_settings()
        if not is_livekit_configured(settings):
            return {"enabled": False}

        body = await read_optional_json(request)
        raw_room = body.get("room")
        room = raw_room if isinstance(raw_room, str) and raw_room else ""
        raw_thread_id = body.get("threadId", body.get("thread_id"))
        thread_id = raw_thread_id if isinstance(raw_thread_id, str) and raw_thread_id else None
        raw_participant_identity = body.get(
            "participantIdentity",
            body.get("participant_identity"),
        )
        participant_identity = (
            raw_participant_identity
            if isinstance(raw_participant_identity, str) and raw_participant_identity
            else ""
        )

        try:
            await dispatch_livekit_agent(
                settings,
                room=room,
                thread_id=thread_id,
                participant_identity=participant_identity,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LiveKitAgentDispatchError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return {"enabled": True, "dispatched": True}

    return router
