"""Speech pipeline settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SttSettings:
    enabled: bool
    transcriptions_url: str
    model: str
    api_key: str = ""
    language: str = ""
    timeout_seconds: int = 30
    submit_to_chat: bool = True


@dataclass(frozen=True)
class VadSettings:
    threshold: float = 0.5
    min_speech_ms: int = 250
    min_silence_ms: int = 700
    speech_pad_ms: int = 200
    max_utterance_ms: int = 20000


@dataclass(frozen=True)
class TtsSettings:
    enabled: bool
    speech_url: str
    model: str = "kokoro"
    voice: str = "af_heart"
    api_key: str = ""
    response_format: str = "pcm"
    speed: float = 1.0
    timeout_seconds: int = 60


def settings_from_app_settings(settings: Any) -> tuple[SttSettings, VadSettings, TtsSettings]:
    return (
        SttSettings(
            enabled=bool(settings.stt_enabled),
            transcriptions_url=str(settings.stt_transcriptions_url),
            model=str(settings.stt_model),
            api_key=str(settings.stt_api_key),
            language=str(settings.stt_language),
            timeout_seconds=int(settings.stt_timeout_seconds),
            submit_to_chat=bool(settings.stt_submit_to_chat),
        ),
        VadSettings(
            threshold=float(settings.vad_threshold),
            min_speech_ms=int(settings.vad_min_speech_ms),
            min_silence_ms=int(settings.vad_min_silence_ms),
            speech_pad_ms=int(settings.vad_speech_pad_ms),
            max_utterance_ms=int(settings.vad_max_utterance_ms),
        ),
        TtsSettings(
            enabled=bool(settings.tts_enabled),
            speech_url=str(settings.tts_speech_url),
            model=str(settings.tts_model),
            voice=str(settings.tts_voice),
            api_key=str(settings.tts_api_key),
            response_format=str(settings.tts_response_format),
            speed=float(settings.tts_speed),
            timeout_seconds=int(settings.tts_timeout_seconds),
        ),
    )
