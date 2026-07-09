"""Build LiveKit STT/TTS plugins from the OpenAI-compatible speech settings.

The project points STT/TTS at OpenAI-compatible endpoints (e.g. self-hosted
transcription and text-to-speech services). These helpers translate the ``Settings``
speech fields into the kwargs the ``livekit.plugins.openai`` STT/TTS clients
expect, falling back to the shared OpenAI LLM credentials when no dedicated
speech endpoint is configured.
"""

from __future__ import annotations

from typing import Any

from wotbot.core.settings import Settings


def _base_url_from_openai_endpoint(endpoint: str, *, suffix: str) -> str:
    normalized = endpoint.strip().rstrip("/")
    if not normalized:
        return ""
    if normalized.endswith(suffix):
        return normalized[: -len(suffix)].rstrip("/")
    return normalized


def _maybe_set(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value or None


def _speech_api_key(*, endpoint_url: str, speech_api_key: str, openai_api_key: str) -> str:
    if _maybe_set(endpoint_url):
        return speech_api_key.strip()
    return speech_api_key.strip() or openai_api_key.strip()


def stt_kwargs(settings: Settings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": settings.stt_model}
    language = _maybe_set(settings.stt_language)
    if language:
        kwargs["language"] = language
    else:
        kwargs["detect_language"] = True
    base_url = (
        _base_url_from_openai_endpoint(
            settings.stt_transcriptions_url,
            suffix="/audio/transcriptions",
        )
        or settings.openai_base_url
    )
    api_key = _speech_api_key(
        endpoint_url=settings.stt_transcriptions_url,
        speech_api_key=settings.stt_api_key,
        openai_api_key=settings.openai_api_key,
    )
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    return kwargs


def tts_kwargs(settings: Settings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": settings.tts_model,
        "voice": settings.tts_voice,
        "speed": settings.tts_speed,
    }
    base_url = (
        _base_url_from_openai_endpoint(
            settings.tts_speech_url,
            suffix="/audio/speech",
        )
        or settings.openai_base_url
    )
    api_key = _speech_api_key(
        endpoint_url=settings.tts_speech_url,
        speech_api_key=settings.tts_api_key,
        openai_api_key=settings.openai_api_key,
    )
    response_format = _maybe_set(settings.tts_response_format)
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    if response_format:
        kwargs["response_format"] = response_format
    return kwargs


def make_stt(settings: Settings):
    from livekit.plugins import openai

    return openai.STT(**stt_kwargs(settings))


def make_tts(settings: Settings):
    from livekit.plugins import openai

    return openai.TTS(**tts_kwargs(settings))
