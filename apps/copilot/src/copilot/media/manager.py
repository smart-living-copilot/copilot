"""Speech pipeline lifecycle and text-to-speech playback management."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from threading import Lock
from typing import Any, Protocol

from copilot.media.audio import Pcm16FrameChunker, TTS_FRAME_SAMPLES, TTS_OUTPUT_SAMPLE_RATE
from copilot.media.clients import (
    OpenAICompatibleSpeechToTextClient,
    OpenAICompatibleTextToSpeechClient,
)
from copilot.media.pipeline import SpeechPipeline
from copilot.media.settings import (
    SttSettings,
    TtsSettings,
    VadSettings,
    settings_from_app_settings,
)
from copilot.media.vad import SileroSpeechProbabilityDetector, VadUtteranceSegmenter

logger = logging.getLogger(__name__)
TTS_OUTPUT_FRAME_SECONDS = TTS_FRAME_SAMPLES / TTS_OUTPUT_SAMPLE_RATE

type TranscriptSubmitter = Callable[[str, str], Awaitable[str]]
type TranscriptStreamer = Callable[[str, str], AsyncIterator[str]]


class SpeechMediaSessionRegistry(Protocol):
    def add_transcript(self, session_id: str, webrtc_id: str | None = None) -> str: ...

    def complete_transcript(
        self,
        transcript_id: str,
        text: str,
        webrtc_id: str | None = None,
    ) -> str | None: ...

    def submit_transcript(self, transcript_id: str) -> None: ...

    def fail_transcript(self, transcript_id: str, error: str) -> None: ...

    def record_assistant_response(self, webrtc_id: str | None, text: str) -> None: ...

    def record_assistant_response_delta(self, webrtc_id: str | None, text: str) -> None: ...

    def start_tts(self, webrtc_id: str, text: str) -> None: ...

    def record_tts_audio_frame(self, webrtc_id: str) -> None: ...

    def fail_tts(self, webrtc_id: str, error: str) -> None: ...


class SpeechPipelineManager:
    def __init__(self, media_sessions: SpeechMediaSessionRegistry) -> None:
        self._media_sessions = media_sessions
        self._lock = Lock()
        self._pipelines_by_key: dict[str, SpeechPipeline] = {}
        self._stt_settings: SttSettings | None = None
        self._vad_settings: VadSettings | None = None
        self._tts_settings: TtsSettings | None = None
        self._submit_transcript: TranscriptSubmitter | None = None
        self._stream_transcript: TranscriptStreamer | None = None
        self._tts_client: OpenAICompatibleTextToSpeechClient | None = None
        self._outbound_audio_by_webrtc_id: dict[str, asyncio.Queue] = {}
        self._playback_epoch_by_webrtc_id: dict[str, int] = {}
        self._next_output_at_by_webrtc_id: dict[str, float] = {}

    def configure(
        self,
        settings: Any,
        submit_transcript: TranscriptSubmitter | None,
        stream_transcript: TranscriptStreamer | None = None,
    ) -> None:
        stt_settings, vad_settings, tts_settings = settings_from_app_settings(settings)
        with self._lock:
            self._stt_settings = stt_settings
            self._vad_settings = vad_settings
            self._tts_settings = tts_settings
            self._submit_transcript = submit_transcript if stt_settings.submit_to_chat else None
            self._stream_transcript = stream_transcript if stt_settings.submit_to_chat else None
            self._tts_client = (
                OpenAICompatibleTextToSpeechClient(tts_settings) if tts_settings.enabled else None
            )

    def get_or_create(self, session_id: str, *, webrtc_id: str | None) -> SpeechPipeline | None:
        with self._lock:
            if self._stt_settings is None or self._vad_settings is None:
                return None
            if not self._stt_settings.enabled:
                return None
            if not self._stt_settings.transcriptions_url.strip():
                logger.warning(
                    "STT is enabled but STT_TRANSCRIPTIONS_URL is empty; speech pipeline disabled"
                )
                return None

            key = webrtc_id or session_id
            existing = self._pipelines_by_key.get(key)
            if existing is not None:
                existing.set_webrtc_id(webrtc_id)
                return existing

            if webrtc_id and session_id in self._pipelines_by_key:
                existing = self._pipelines_by_key.pop(session_id)
                existing.set_webrtc_id(webrtc_id)
                self._pipelines_by_key[webrtc_id] = existing
                return existing

            detector = SileroSpeechProbabilityDetector()
            pipeline = SpeechPipeline(
                session_id=session_id,
                stt_client=OpenAICompatibleSpeechToTextClient(self._stt_settings),
                segmenter=VadUtteranceSegmenter(self._vad_settings, detector),
                submit_transcript=self._submit_transcript,
                synthesize_response=self.synthesize_response,
                on_speech_started=self.interrupt_playback,
                run_assistant_work=self.run_with_work_indicator,
                on_transcript_started=self._media_sessions.add_transcript,
                on_transcript_completed=self._media_sessions.complete_transcript,
                on_transcript_submitted=self._media_sessions.submit_transcript,
                on_transcript_failed=self._media_sessions.fail_transcript,
                on_assistant_response=self._media_sessions.record_assistant_response,
                on_assistant_response_delta=self._media_sessions.record_assistant_response_delta,
                stream_transcript=self._stream_transcript,
            )
            self._pipelines_by_key[key] = pipeline

        async def start_pipeline() -> None:
            await detector.load()
            pipeline.start()

        task = asyncio.create_task(start_pipeline())
        task.add_done_callback(self._log_start_task_result)
        return pipeline

    async def stop(self, webrtc_id: str) -> None:
        with self._lock:
            pipeline = self._pipelines_by_key.pop(webrtc_id, None)
            self._outbound_audio_by_webrtc_id.pop(webrtc_id, None)
            self._playback_epoch_by_webrtc_id.pop(webrtc_id, None)
            self._next_output_at_by_webrtc_id.pop(webrtc_id, None)
        if pipeline is not None:
            await pipeline.close(flush=True)

    async def stop_all(self) -> None:
        with self._lock:
            pipelines = list(
                {id(pipeline): pipeline for pipeline in self._pipelines_by_key.values()}.values()
            )
            self._pipelines_by_key = {}
            self._outbound_audio_by_webrtc_id = {}
            self._playback_epoch_by_webrtc_id = {}
            self._next_output_at_by_webrtc_id = {}
        for pipeline in pipelines:
            await pipeline.close(flush=True)

    async def synthesize_response(self, webrtc_id: str | None, text: str) -> None:
        if not webrtc_id or not text.strip():
            return
        with self._lock:
            tts_client = self._tts_client
        if tts_client is None:
            return

        playback_epoch = self._current_playback_epoch(webrtc_id)
        self._media_sessions.start_tts(webrtc_id, text)
        audio_chunks = 0
        audio_frames = 0
        chunker = Pcm16FrameChunker()
        try:
            async for audio_bytes in tts_client.stream_pcm(text):
                if not self._is_playback_epoch_current(webrtc_id, playback_epoch):
                    logger.debug("Discarding stale TTS audio for media session %s", webrtc_id)
                    return
                audio_chunks += 1
                for frame in chunker.accept(audio_bytes):
                    audio_frames += 1
                    queued = await self.enqueue_output_audio(
                        webrtc_id,
                        frame,
                        playback_epoch=playback_epoch,
                    )
                    if not queued:
                        logger.debug(
                            "Stopped queuing stale TTS audio for media session %s", webrtc_id
                        )
                        return
            for frame in chunker.flush():
                audio_frames += 1
                queued = await self.enqueue_output_audio(
                    webrtc_id,
                    frame,
                    playback_epoch=playback_epoch,
                )
                if not queued:
                    logger.debug("Stopped queuing stale TTS audio for media session %s", webrtc_id)
                    return
            logger.info(
                "Queued TTS audio for media session %s chunks=%s frames=%s",
                webrtc_id,
                audio_chunks,
                audio_frames,
            )
        except Exception as exc:
            logger.exception(
                "Failed to synthesize TTS audio for media session %s",
                webrtc_id,
            )
            self._media_sessions.fail_tts(webrtc_id, str(exc))

    async def run_with_work_indicator(
        self,
        webrtc_id: str | None,
        operation: Awaitable[str],
    ) -> str:
        if not webrtc_id:
            return await operation

        indicator_task = asyncio.create_task(self._play_work_indicator(webrtc_id))
        try:
            return await operation
        finally:
            indicator_task.cancel()
            with suppress(asyncio.CancelledError):
                await indicator_task

    def interrupt_playback(self, webrtc_id: str | None) -> None:
        if not webrtc_id:
            return
        with self._lock:
            self._playback_epoch_by_webrtc_id[webrtc_id] = (
                self._playback_epoch_by_webrtc_id.get(webrtc_id, 0) + 1
            )
            self._next_output_at_by_webrtc_id[webrtc_id] = time.monotonic()
            queue = self._outbound_audio_by_webrtc_id.get(webrtc_id)
            cleared = 0
            if queue is not None:
                while True:
                    try:
                        queue.get_nowait()
                        cleared += 1
                    except asyncio.QueueEmpty:
                        break
        if cleared:
            logger.info(
                "Interrupted media playback webrtc_id=%s cleared_frames=%s", webrtc_id, cleared
            )

    async def enqueue_output_audio(
        self,
        webrtc_id: str,
        frame: Any,
        *,
        record_tts: bool = True,
        playback_epoch: int | None = None,
    ) -> bool:
        queued = False
        with self._lock:
            frame_epoch = (
                playback_epoch
                if playback_epoch is not None
                else self._playback_epoch_by_webrtc_id.get(webrtc_id, 0)
            )
            if (
                playback_epoch is not None
                and self._playback_epoch_by_webrtc_id.get(webrtc_id, 0) != frame_epoch
            ):
                return False
            queue = self._output_queue_locked(webrtc_id)
            try:
                queue.put_nowait((frame_epoch, frame))
                queued = True
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait((frame_epoch, frame))
                queued = True
        if record_tts:
            self._media_sessions.record_tts_audio_frame(webrtc_id)
        return queued

    async def next_output_audio(self, webrtc_id: str | None) -> tuple[int, Any] | None:
        if not webrtc_id:
            await asyncio.sleep(0.05)
            return None
        queue = self._output_queue(webrtc_id)
        deadline = time.monotonic() + 0.05
        while True:
            timeout = max(0.0, deadline - time.monotonic())
            try:
                frame_epoch, frame = await asyncio.wait_for(queue.get(), timeout=timeout)
            except TimeoutError:
                return None
            if not self._is_playback_epoch_current(webrtc_id, frame_epoch):
                continue

            await self._pace_output_audio(webrtc_id)
            if not self._is_playback_epoch_current(webrtc_id, frame_epoch):
                return None
            return (TTS_OUTPUT_SAMPLE_RATE, frame)

    def _output_queue(self, webrtc_id: str) -> asyncio.Queue:
        with self._lock:
            return self._output_queue_locked(webrtc_id)

    def _output_queue_locked(self, webrtc_id: str) -> asyncio.Queue:
        queue = self._outbound_audio_by_webrtc_id.get(webrtc_id)
        if queue is None:
            queue = asyncio.Queue(maxsize=2048)
            self._outbound_audio_by_webrtc_id[webrtc_id] = queue
        return queue

    def _current_playback_epoch(self, webrtc_id: str) -> int:
        with self._lock:
            return self._playback_epoch_by_webrtc_id.get(webrtc_id, 0)

    def _is_playback_epoch_current(self, webrtc_id: str, playback_epoch: int) -> bool:
        with self._lock:
            return self._playback_epoch_by_webrtc_id.get(webrtc_id, 0) == playback_epoch

    async def _pace_output_audio(self, webrtc_id: str) -> None:
        with self._lock:
            now = time.monotonic()
            next_output_at = self._next_output_at_by_webrtc_id.get(webrtc_id)
            if next_output_at is None or next_output_at <= now:
                self._next_output_at_by_webrtc_id[webrtc_id] = now + TTS_OUTPUT_FRAME_SECONDS
                return
            self._next_output_at_by_webrtc_id[webrtc_id] = next_output_at + TTS_OUTPUT_FRAME_SECONDS
            delay = next_output_at - now
        await asyncio.sleep(delay)

    async def _play_work_indicator(self, webrtc_id: str) -> None:
        playback_epoch = self._current_playback_epoch(webrtc_id)
        await asyncio.sleep(0.7)
        while True:
            for frame in self._work_indicator_frames():
                queued = await self.enqueue_output_audio(
                    webrtc_id,
                    frame,
                    record_tts=False,
                    playback_epoch=playback_epoch,
                )
                if not queued:
                    return
            await asyncio.sleep(1.3)

    @staticmethod
    def _work_indicator_frames() -> list[Any]:
        import numpy as np

        sample_rate = TTS_OUTPUT_SAMPLE_RATE
        duration_seconds = 0.12
        sample_count = round(sample_rate * duration_seconds)
        time_axis = np.arange(sample_count, dtype=np.float32) / sample_rate
        envelope = np.sin(np.linspace(0.0, np.pi, sample_count, dtype=np.float32))
        tone = 0.055 * envelope * np.sin(2.0 * np.pi * 660.0 * time_axis)
        return [
            tone[index : index + 480].astype(np.float32, copy=True)
            for index in range(0, tone.size, 480)
        ]

    @staticmethod
    def _log_start_task_result(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Failed to start speech pipeline")
