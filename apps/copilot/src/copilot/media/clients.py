"""OpenAI-compatible speech HTTP clients."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from copilot.media.settings import SttSettings, TtsSettings
from copilot.media.types import TranscriptResult

logger = logging.getLogger(__name__)


class OpenAICompatibleSpeechToTextClient:
    def __init__(
        self,
        settings: SttSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def transcribe_wav(self, wav_bytes: bytes) -> TranscriptResult:
        headers = {"Accept": "application/json"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"

        data = {
            "model": self._settings.model,
            "stream": "false",
        }
        if self._settings.language:
            data["language"] = self._settings.language

        files = {
            "file": ("utterance.wav", wav_bytes, "audio/wav"),
        }

        async with httpx.AsyncClient(
            timeout=self._settings.timeout_seconds,
            transport=self._transport,
        ) as client:
            response = await client.post(
                self._settings.transcriptions_url,
                headers=headers,
                data=data,
                files=files,
            )
        response.raise_for_status()
        payload = response.json()
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str):
            raise ValueError("Transcription response did not contain a text field")
        return TranscriptResult(text=text.strip())


class OpenAICompatibleTextToSpeechClient:
    def __init__(
        self,
        settings: TtsSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def build_speech_payload(self, text: str) -> dict[str, Any]:
        return {
            "input": text,
            "model": self._settings.model,
            "voice": self._settings.voice,
            "response_format": self._settings.response_format,
            "speed": self._settings.speed,
        }

    async def stream_pcm(self, text: str):
        headers: dict[str, str] = {"Accept": "audio/*"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"
        logger.info(
            "Requesting TTS stream url=%s model=%s voice=%s format=%s text_chars=%d",
            self._settings.speech_url,
            self._settings.model,
            self._settings.voice,
            self._settings.response_format,
            len(text),
        )

        async with httpx.AsyncClient(
            timeout=self._settings.timeout_seconds,
            transport=self._transport,
        ) as client:
            async with client.stream(
                "POST",
                self._settings.speech_url,
                headers=headers,
                json=self.build_speech_payload(text),
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
