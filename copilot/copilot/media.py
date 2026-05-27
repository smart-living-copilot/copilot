"""Browser media ingress for future multimodal model input."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from copilot.speech import (
    OpenAICompatibleSpeechToTextClient,
    OpenAICompatibleTextToSpeechClient,
    Pcm16FrameChunker,
    SileroSpeechProbabilityDetector,
    SpeechPipeline,
    SttSettings,
    TTS_FRAME_SAMPLES,
    TTS_OUTPUT_SAMPLE_RATE,
    TtsSettings,
    VadSettings,
    VadUtteranceSegmenter,
    new_transcript_id,
    settings_from_app_settings,
)

logger = logging.getLogger(__name__)
TTS_OUTPUT_FRAME_SECONDS = TTS_FRAME_SAMPLES / TTS_OUTPUT_SAMPLE_RATE

type TranscriptSubmitter = Callable[[str, str], Awaitable[str]]
type TranscriptStreamer = Callable[[str, str], AsyncIterator[str]]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class MediaTranscript:
    id: str
    created_at: str
    updated_at: str
    status: str
    webrtc_id: str | None = None
    thread_id: str | None = None
    text: str = ""
    error: str | None = None


@dataclass
class MediaSessionStats:
    id: str
    created_at: str
    updated_at: str
    status: str = "active"
    webrtc_id: str | None = None
    thread_id: str | None = None
    audio_frames: int = 0
    audio_samples: int = 0
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    video_frames: int = 0
    video_width: int | None = None
    video_height: int | None = None
    transcript_count: int = 0
    latest_transcript_text: str | None = None
    latest_assistant_text: str | None = None
    assistant_response_pending: bool = False
    transcripts: list[MediaTranscript] = field(default_factory=list)
    tts_requests: int = 0
    tts_audio_frames: int = 0
    latest_tts_text: str | None = None
    latest_tts_error: str | None = None


class MediaSessionRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[str, MediaSessionStats] = {}

    def ensure(self, session_id: str, *, webrtc_id: str | None = None) -> MediaSessionStats:
        now = _utc_now()
        key = webrtc_id or session_id
        with self._lock:
            stats = self._sessions.get(key)
            if stats is None and webrtc_id and session_id in self._sessions:
                stats = self._sessions.pop(session_id)
                self._sessions[key] = stats
            if stats is None:
                stats = MediaSessionStats(
                    id=session_id,
                    webrtc_id=webrtc_id,
                    created_at=now,
                    updated_at=now,
                )
                self._sessions[key] = stats
            if webrtc_id:
                stats.webrtc_id = webrtc_id
            stats.updated_at = now
            stats.status = "active"
            return stats

    def set_metadata(self, webrtc_id: str, *, thread_id: str | None) -> MediaSessionStats:
        stats = self.ensure(webrtc_id, webrtc_id=webrtc_id)
        with self._lock:
            stats.thread_id = thread_id
            stats.updated_at = _utc_now()
            for transcript in stats.transcripts:
                if transcript.thread_id is None:
                    transcript.thread_id = thread_id
                    transcript.updated_at = stats.updated_at
            return stats

    def record_audio(
        self,
        session_id: str,
        *,
        webrtc_id: str | None,
        sample_rate: int,
        samples: int,
        channels: int | None,
    ) -> None:
        stats = self.ensure(session_id, webrtc_id=webrtc_id)
        with self._lock:
            stats.audio_frames += 1
            stats.audio_samples += samples
            stats.audio_sample_rate = sample_rate
            stats.audio_channels = channels
            stats.updated_at = _utc_now()

    def record_video(
        self,
        session_id: str,
        *,
        webrtc_id: str | None,
        width: int,
        height: int,
    ) -> None:
        stats = self.ensure(session_id, webrtc_id=webrtc_id)
        with self._lock:
            stats.video_frames += 1
            stats.video_width = width
            stats.video_height = height
            stats.updated_at = _utc_now()

    def close(self, session_id: str, *, webrtc_id: str | None = None) -> None:
        key = webrtc_id or session_id
        with self._lock:
            stats = self._sessions.get(key)
            if stats is None and webrtc_id:
                stats = self._sessions.get(session_id)
            if stats is None:
                return
            stats.status = "closed"
            stats.updated_at = _utc_now()

    def add_transcript(self, session_id: str, webrtc_id: str | None = None) -> str:
        transcript_id = new_transcript_id()
        now = _utc_now()
        stats = self.ensure(session_id, webrtc_id=webrtc_id)
        with self._lock:
            transcript = MediaTranscript(
                id=transcript_id,
                created_at=now,
                updated_at=now,
                status="transcribing",
                webrtc_id=stats.webrtc_id,
                thread_id=stats.thread_id,
            )
            stats.transcripts.append(transcript)
            stats.transcript_count = len(stats.transcripts)
            stats.updated_at = now
            return transcript_id

    def complete_transcript(
        self,
        transcript_id: str,
        text: str,
        webrtc_id: str | None = None,
    ) -> str | None:
        with self._lock:
            transcript, stats = self._find_transcript_locked(transcript_id)
            if transcript is None or stats is None:
                return None
            if webrtc_id:
                transcript.webrtc_id = webrtc_id
            transcript.text = text
            transcript.error = None
            transcript.thread_id = stats.thread_id
            transcript.status = "transcribed" if stats.thread_id else "not_submitted"
            transcript.updated_at = _utc_now()
            stats.latest_transcript_text = text
            stats.latest_assistant_text = None
            stats.assistant_response_pending = stats.thread_id is not None
            stats.transcript_count = len(stats.transcripts)
            stats.updated_at = transcript.updated_at
            return stats.thread_id

    def submit_transcript(self, transcript_id: str) -> None:
        with self._lock:
            transcript, stats = self._find_transcript_locked(transcript_id)
            if transcript is None or stats is None:
                return
            transcript.status = "submitted"
            transcript.updated_at = _utc_now()
            stats.assistant_response_pending = False
            stats.updated_at = transcript.updated_at

    def record_assistant_response(self, webrtc_id: str | None, text: str) -> None:
        if not webrtc_id or not text.strip():
            return
        stats = self.ensure(webrtc_id, webrtc_id=webrtc_id)
        with self._lock:
            stats.latest_assistant_text = text.strip()
            stats.assistant_response_pending = False
            stats.updated_at = _utc_now()

    def record_assistant_response_delta(self, webrtc_id: str | None, text: str) -> None:
        self.record_assistant_response(webrtc_id, text)

    def fail_transcript(self, transcript_id: str, error: str) -> None:
        with self._lock:
            transcript, stats = self._find_transcript_locked(transcript_id)
            if transcript is None or stats is None:
                return
            transcript.status = "failed"
            transcript.error = error
            transcript.updated_at = _utc_now()
            stats.assistant_response_pending = False
            stats.updated_at = transcript.updated_at

    def start_tts(self, webrtc_id: str, text: str) -> None:
        stats = self.ensure(webrtc_id, webrtc_id=webrtc_id)
        with self._lock:
            stats.tts_requests += 1
            stats.latest_tts_text = text
            stats.latest_tts_error = None
            stats.updated_at = _utc_now()

    def record_tts_audio_frame(self, webrtc_id: str) -> None:
        stats = self.ensure(webrtc_id, webrtc_id=webrtc_id)
        with self._lock:
            stats.tts_audio_frames += 1
            stats.updated_at = _utc_now()

    def fail_tts(self, webrtc_id: str, error: str) -> None:
        stats = self.ensure(webrtc_id, webrtc_id=webrtc_id)
        with self._lock:
            stats.latest_tts_error = error
            stats.updated_at = _utc_now()

    def _find_transcript_locked(
        self,
        transcript_id: str,
    ) -> tuple[MediaTranscript | None, MediaSessionStats | None]:
        for stats in self._sessions.values():
            for transcript in stats.transcripts:
                if transcript.id == transcript_id:
                    return transcript, stats
        return None, None

    def remove(self, webrtc_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(webrtc_id, None) is not None

    def get(self, webrtc_id: str) -> dict[str, Any] | None:
        with self._lock:
            stats = self._sessions.get(webrtc_id)
            return asdict(stats) if stats is not None else None

    def snapshots(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(stats) for stats in self._sessions.values()]

    def latest_text_fields(
        self,
        webrtc_id: str,
    ) -> tuple[str | None, str | None, bool] | None:
        """Atomically read the fields the live snapshot stream watches.

        Returns ``None`` if the session is unknown, otherwise the
        ``(latest_transcript_text, latest_assistant_text, assistant_pending)``
        tuple. This avoids the full ``asdict`` deep copy that ``get`` performs
        on every poll tick.
        """
        with self._lock:
            stats = self._sessions.get(webrtc_id)
            if stats is None:
                return None
            return (
                stats.latest_transcript_text,
                stats.latest_assistant_text,
                stats.assistant_response_pending,
            )


media_sessions = MediaSessionRegistry()


class SpeechPipelineManager:
    def __init__(self) -> None:
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
                on_transcript_started=media_sessions.add_transcript,
                on_transcript_completed=media_sessions.complete_transcript,
                on_transcript_submitted=media_sessions.submit_transcript,
                on_transcript_failed=media_sessions.fail_transcript,
                on_assistant_response=media_sessions.record_assistant_response,
                on_assistant_response_delta=media_sessions.record_assistant_response_delta,
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
        media_sessions.start_tts(webrtc_id, text)
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
            media_sessions.fail_tts(webrtc_id, str(exc))

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
            media_sessions.record_tts_audio_frame(webrtc_id)
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


speech_pipelines = SpeechPipelineManager()


def _current_webrtc_id() -> str | None:
    try:
        from fastrtc.utils import current_context
    except ModuleNotFoundError:
        return None

    try:
        context = current_context.get()
    except LookupError:
        return None

    webrtc_id = getattr(context, "webrtc_id", None)
    return webrtc_id if isinstance(webrtc_id, str) and webrtc_id else None


def parse_rtc_configuration(raw_json: str | None) -> dict[str, Any]:
    if not raw_json:
        return {"iceServers": [{"urls": "stun:stun.l.google.com:19302"}]}

    import json

    parsed = json.loads(raw_json)
    if not isinstance(parsed, dict):
        raise ValueError("RTC configuration must be a JSON object")
    ice_servers = parsed.get("iceServers")
    if ice_servers is not None and not isinstance(ice_servers, list):
        raise ValueError("RTC configuration iceServers must be a list")
    return parsed


def create_media_stream():
    try:
        import numpy as np
        from fastrtc import AsyncAudioVideoStreamHandler, Stream, wait_for_item
    except ModuleNotFoundError as exc:
        logger.warning("FastRTC is not installed; media ingress routes are disabled: %s", exc)
        return None

    class MediaIngressHandler(AsyncAudioVideoStreamHandler):
        def __init__(self) -> None:
            super().__init__(
                "mono",
                input_sample_rate=16000,
                output_sample_rate=24000,
                fps=15,
            )
            self.session_id = f"media-{uuid.uuid4()}"
            self._last_webrtc_id: str | None = None
            self._video_queue = asyncio.Queue(maxsize=1)
            self._last_log_at = 0.0

        def copy(self):
            return MediaIngressHandler()

        def _webrtc_id(self) -> str | None:
            webrtc_id = _current_webrtc_id()
            if webrtc_id:
                self._last_webrtc_id = webrtc_id
            return self._last_webrtc_id

        async def receive(self, frame) -> None:
            sample_rate, audio = frame
            webrtc_id = self._webrtc_id()
            samples = int(audio.shape[-1]) if hasattr(audio, "shape") else 0
            channels = int(audio.shape[0]) if getattr(audio, "ndim", 0) > 1 else 1
            media_sessions.record_audio(
                self.session_id,
                webrtc_id=webrtc_id,
                sample_rate=int(sample_rate),
                samples=samples,
                channels=channels,
            )
            pipeline = speech_pipelines.get_or_create(self.session_id, webrtc_id=webrtc_id)
            if pipeline is not None:
                pipeline.enqueue_audio(int(sample_rate), audio)
            self._log_progress()

        async def emit(self):
            return await speech_pipelines.next_output_audio(self._last_webrtc_id)

        async def video_receive(self, frame) -> None:
            height, width = frame.shape[:2]
            media_sessions.record_video(
                self.session_id,
                webrtc_id=self._webrtc_id(),
                width=int(width),
                height=int(height),
            )
            if self._video_queue.full():
                self._video_queue.get_nowait()
            self._video_queue.put_nowait(frame)
            self._log_progress()

        async def video_emit(self):
            frame = await wait_for_item(self._video_queue, 0.05)
            if frame is not None:
                return frame
            return np.zeros((100, 100, 3), dtype=np.uint8)

        async def shutdown(self) -> None:
            await speech_pipelines.stop(self._last_webrtc_id or self.session_id)
            media_sessions.close(self.session_id, webrtc_id=self._last_webrtc_id)

        def _log_progress(self) -> None:
            now = time.monotonic()
            if now - self._last_log_at < 10:
                return
            self._last_log_at = now
            logger.info(
                "Receiving browser media session=%s webrtc_id=%s",
                self.session_id,
                self._last_webrtc_id,
            )

    server_rtc_configuration = None
    try:
        server_rtc_configuration = parse_rtc_configuration(
            os.getenv("MEDIA_SERVER_RTC_CONFIGURATION")
        )
    except ValueError:
        logger.exception("Ignoring invalid MEDIA_SERVER_RTC_CONFIGURATION")

    return Stream(
        handler=MediaIngressHandler(),
        modality="audio-video",
        mode="send-receive",
        concurrency_limit=5,
        time_limit=None,
        server_rtc_configuration=server_rtc_configuration,
        ui_args={"hide_title": True, "full_screen": False},
    )
