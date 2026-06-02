from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
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
TTS_CACHE_TTL_SECONDS = 30 * 60

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
    url = f"{base_url}/audio/speech"
    response_format = "mp3"
    body: dict[str, Any] = {
        "model": kwargs["model"],
        "voice": kwargs["voice"],
        "input": text,
        "speed": kwargs["speed"],
        "response_format": response_format,
    }
    cache_key = _tts_cache_key(url, body)
    cached = _read_tts_cache(cache_key)
    if cached is not None:
        content, content_type = cached
        return _speech_response(content, content_type, cache_status="hit")

    response = await _post_json(
        url,
        body,
        api_key=api_key,
        accept="audio/mpeg",
    )
    content_type = response.headers.get("content-type") or "audio/mpeg"
    _write_tts_cache(cache_key, response.content, content_type)
    return _speech_response(response.content, content_type, cache_status="miss")


def _speech_response(content: bytes, content_type: str, *, cache_status: str) -> Response:
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
            "X-Speech-Cache": cache_status,
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


def _tts_cache_key(url: str, body: dict[str, Any]) -> str:
    payload = json.dumps(
        {"url": url, "body": body},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _tts_cache_dir() -> Path:
    return Path(tempfile.gettempdir()) / "smart-living-copilot-tts-cache"


def _read_tts_cache(cache_key: str) -> tuple[bytes, str] | None:
    cache_dir = _tts_cache_dir()
    body_path = cache_dir / f"{cache_key}.body"
    meta_path = cache_dir / f"{cache_key}.json"
    now = time.time()

    try:
        if now - body_path.stat().st_mtime > TTS_CACHE_TTL_SECONDS:
            _delete_tts_cache_entry(body_path, meta_path)
            return None
        content = body_path.read_bytes()
        content_type = "audio/mpeg"
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(metadata, dict):
                content_type = str(metadata.get("content_type") or content_type)
        return content, content_type
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return None


def _write_tts_cache(cache_key: str, content: bytes, content_type: str) -> None:
    cache_dir = _tts_cache_dir()
    body_path = cache_dir / f"{cache_key}.body"
    meta_path = cache_dir / f"{cache_key}.json"
    body_tmp_path = cache_dir / f"{cache_key}.body.tmp"
    meta_tmp_path = cache_dir / f"{cache_key}.json.tmp"
    now = time.time()

    try:
        cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        _prune_expired_tts_cache(cache_dir, now)
        body_tmp_path.write_bytes(content)
        meta_tmp_path.write_text(
            json.dumps({"content_type": content_type}, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(body_tmp_path, body_path)
        os.replace(meta_tmp_path, meta_path)
    except OSError:
        _delete_tts_cache_entry(body_tmp_path, meta_tmp_path)


def _prune_expired_tts_cache(cache_dir: Path, now: float) -> None:
    try:
        body_paths = list(cache_dir.glob("*.body"))
    except OSError:
        return

    for body_path in body_paths:
        try:
            if now - body_path.stat().st_mtime > TTS_CACHE_TTL_SECONDS:
                _delete_tts_cache_entry(body_path, body_path.with_suffix(".json"))
        except OSError:
            continue


def _delete_tts_cache_entry(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


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
