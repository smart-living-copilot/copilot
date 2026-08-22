"""Build LiveKit STT/TTS plugins from the OpenAI-compatible speech settings.

The project points STT/TTS at OpenAI-compatible endpoints (e.g. self-hosted
transcription and text-to-speech services, or an aggregator like OpenRouter).
These helpers translate the ``Settings`` speech fields into the kwargs the
``livekit.plugins.openai`` STT/TTS clients expect, falling back to the shared
OpenAI LLM credentials when no dedicated speech endpoint is configured.

``livekit.plugins.openai.TTS`` picks its response decoder from the model name:
only the literal ``tts-1``/``tts-1-hd`` get the raw-audio reader, everything
else is assumed to be an OpenAI token-billed model that answers
``stream_format="sse"`` with ``speech.audio.delta`` events. Third-party
endpoints keep their own model names, so they land on the SSE reader whether
or not they speak it: Speaches does, OpenRouter does not -- it ignores
``stream_format`` and always replies with raw ``audio/pcm``. That body holds no
``data:`` lines, so the reader pushes no frames and the request dies on
``APIError: no audio frames were pushed``. ``TTS_STREAM_FORMAT`` picks the
decoder from configuration instead of guessing from the model name.
"""

from __future__ import annotations

from typing import Any

from wotbot.core.settings import Settings, TtsStreamFormat


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


def _raw_audio_tts_class():
    """A TTS that always reads the response body as raw audio bytes."""

    from livekit.agents import APIConnectOptions, tts
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
    from livekit.plugins import openai
    from livekit.plugins.openai.tts import AudioChunkedStream

    class RawAudioTTS(openai.TTS):
        def synthesize(
            self,
            text: str,
            *,
            conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        ) -> tts.ChunkedStream:
            return AudioChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    return RawAudioTTS


def _sse_tts_class():
    """A TTS that always reads the response body as ``speech.audio.*`` events."""

    from livekit.agents import APIConnectOptions, tts
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
    from livekit.plugins import openai
    from livekit.plugins.openai.tts import SSEChunkedStream

    class SseTTS(openai.TTS):
        def synthesize(
            self,
            text: str,
            *,
            conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        ) -> tts.ChunkedStream:
            return SSEChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    return SseTTS


def make_tts(settings: Settings):
    from livekit.plugins import openai

    stream_format: TtsStreamFormat = settings.tts_stream_format
    if stream_format == "audio":
        return _raw_audio_tts_class()(**tts_kwargs(settings))
    if stream_format == "sse":
        return _sse_tts_class()(**tts_kwargs(settings))
    return openai.TTS(**tts_kwargs(settings))
