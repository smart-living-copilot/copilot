from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from copilot.core.api_dependencies import verify_internal_api_key
from copilot.core.settings import Settings
from copilot.workers.livekit.speech import stt_kwargs, tts_kwargs

OPENAI_BASE_URL = "https://api.openai.com/v1"
MAX_TTS_CHARS = 4096
MAX_TRANSCRIPTION_BYTES = 25 * 1024 * 1024

router = APIRouter(prefix="/speech", tags=["speech"])


class TextToSpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TTS_CHARS)


@router.post("/tts")
async def create_speech(payload: TextToSpeechRequest, request: Request) -> Response:
    verify_internal_api_key(request)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    settings = _settings(request)
    kwargs = tts_kwargs(settings)
    api_key = str(kwargs.pop("api_key", "") or "")
    base_url = str(kwargs.pop("base_url", "") or OPENAI_BASE_URL).rstrip("/")
    response_format = "mp3"
    body: dict[str, Any] = {
        "model": kwargs["model"],
        "voice": kwargs["voice"],
        "input": text,
        "speed": kwargs["speed"],
        "response_format": response_format,
    }

    response = await _post_json(
        f"{base_url}/audio/speech",
        body,
        api_key=api_key,
        accept="audio/mpeg",
    )
    content_type = response.headers.get("content-type") or "audio/mpeg"
    return Response(
        content=response.content,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/transcriptions")
async def create_transcription(request: Request) -> dict[str, str]:
    verify_internal_api_key(request)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="audio body is required")
    if len(body) > MAX_TRANSCRIPTION_BYTES:
        raise HTTPException(status_code=413, detail="audio body is too large")

    settings = _settings(request)
    kwargs = stt_kwargs(settings)
    api_key = str(kwargs.pop("api_key", "") or "")
    base_url = str(kwargs.pop("base_url", "") or OPENAI_BASE_URL).rstrip("/")
    content_type = request.headers.get("content-type") or "audio/webm"
    filename = request.headers.get("x-filename") or _filename_for_content_type(content_type)
    data: dict[str, str] = {
        "model": str(kwargs["model"]),
        "response_format": "text",
    }
    language = kwargs.get("language")
    if language:
        data["language"] = str(language)

    response = await _post_multipart(
        f"{base_url}/audio/transcriptions",
        data=data,
        files={"file": (filename, body, content_type)},
        api_key=api_key,
    )
    return {"text": _transcription_text(response)}


def _settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return Settings()


async def _post_json(
    url: str,
    body: dict[str, Any],
    *,
    api_key: str,
    accept: str,
) -> httpx.Response:
    headers = {"Accept": accept}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=body, headers=headers)
    if response.is_error:
        raise HTTPException(status_code=502, detail=_upstream_error(response))
    return response


async def _post_multipart(
    url: str,
    *,
    data: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    api_key: str,
) -> httpx.Response:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, data=data, files=files, headers=headers)
    if response.is_error:
        raise HTTPException(status_code=502, detail=_upstream_error(response))
    return response


def _transcription_text(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = response.json()
        except ValueError:
            return response.text.strip()
        if isinstance(data, dict):
            return str(data.get("text") or "").strip()
    return response.text.strip()


def _upstream_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:500] or f"Speech backend returned {response.status_code}"
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or data)[:500]
        detail = data.get("detail")
        if detail:
            return str(detail)[:500]
    return str(data)[:500]


def _filename_for_content_type(content_type: str) -> str:
    if "wav" in content_type:
        return "answer.wav"
    if "mpeg" in content_type or "mp3" in content_type:
        return "answer.mp3"
    if "ogg" in content_type:
        return "answer.ogg"
    return "answer.webm"
