"""FastAPI routes for browser media sessions."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from copilot.media.ingress import media_sessions, parse_rtc_configuration, speech_pipelines


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

    @router.get("/rtc-configuration")
    async def get_media_rtc_configuration(request: Request):
        verify_internal_api_key(request)

        settings = get_settings()
        try:
            raw_configuration = settings.media_rtc_configuration if settings else ""
            configuration = parse_rtc_configuration(raw_configuration)
            configuration["iceGatherTimeoutMs"] = (
                settings.media_ice_gather_timeout_ms if settings else 750
            )
            return configuration
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/sessions")
    async def get_media_sessions(request: Request):
        verify_internal_api_key(request)
        return {"sessions": media_sessions.snapshots()}

    @router.get("/sessions/{webrtc_id}")
    async def get_media_session(webrtc_id: str, request: Request):
        verify_internal_api_key(request)
        stats = media_sessions.get(webrtc_id)
        if stats is None:
            raise HTTPException(status_code=404, detail="Media session not found")
        return stats

    @router.get("/sessions/{webrtc_id}/stream")
    async def stream_media_session(webrtc_id: str, request: Request):
        verify_internal_api_key(request)

        async def event_generator():
            previous: tuple[str | None, str | None, bool] | None = None
            idle_ticks = 0
            missing_ticks = 0
            while True:
                if await request.is_disconnected():
                    return
                current = media_sessions.latest_text_fields(webrtc_id)
                if current is None:
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

    @router.post("/sessions/{webrtc_id}/metadata")
    async def set_media_session_metadata(webrtc_id: str, request: Request):
        verify_internal_api_key(request)
        body = await read_optional_json(request)
        thread_id = body.get("threadId")
        stats = media_sessions.set_metadata(
            webrtc_id,
            thread_id=thread_id if isinstance(thread_id, str) and thread_id else None,
        )
        return jsonable_encoder(stats)

    @router.delete("/sessions/{webrtc_id}")
    async def delete_media_session(webrtc_id: str, request: Request):
        verify_internal_api_key(request)
        await speech_pipelines.stop(webrtc_id)
        return {"ok": media_sessions.remove(webrtc_id)}

    return router
