"""Browser media ingress for future multimodal model input."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from copilot.media.manager import SpeechPipelineManager
from copilot.media.models import MediaSessionStats, MediaTranscript
from copilot.media.pipeline import new_transcript_id

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


_VISION_MAX_DIMENSION = int(os.getenv("VISION_MAX_IMAGE_DIMENSION", "1024"))
_VISION_JPEG_QUALITY = int(os.getenv("VISION_JPEG_QUALITY", "85"))


def encode_frame_to_jpeg(frame: Any) -> bytes | None:
    """Encode a fastrtc video frame (HxWx{3,4} numpy array) to JPEG bytes.

    Returns None on failure rather than raising, since this runs on every
    incoming video frame and must not break the media pipeline.
    """
    try:
        from io import BytesIO

        import numpy as np
        from PIL import Image
    except Exception:  # pragma: no cover - PIL/numpy missing at import time
        logger.warning("Pillow/numpy unavailable; vision frame capture disabled")
        return None

    try:
        if not hasattr(frame, "shape") or frame.ndim < 2:
            return None
        array = np.asarray(frame)
        if array.dtype != np.uint8:
            array = array.astype(np.uint8, copy=False)
        # fastrtc delivers 3-channel frames in BGR order (OpenCV convention),
        # but Pillow treats a 3-channel uint8 array as RGB. Swap so the
        # encoded JPEG actually reflects the real colors.
        if array.ndim == 3 and array.shape[2] >= 3:
            array = array[:, :, :3][:, :, ::-1]
        image = Image.fromarray(array)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.thumbnail((_VISION_MAX_DIMENSION, _VISION_MAX_DIMENSION))
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=_VISION_JPEG_QUALITY)
        return buffer.getvalue()
    except Exception:
        logger.debug("Failed to encode video frame to JPEG", exc_info=True)
        return None


def _public_snapshot(stats: "MediaSessionStats") -> dict[str, Any]:
    data = asdict(stats)
    data.pop("last_video_frame_jpeg", None)
    return data


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

    def store_video_frame_jpeg(
        self,
        session_id: str,
        *,
        webrtc_id: str | None,
        jpeg_bytes: bytes,
    ) -> None:
        stats = self.ensure(session_id, webrtc_id=webrtc_id)
        with self._lock:
            stats.last_video_frame_jpeg = jpeg_bytes
            stats.last_video_frame_at = _utc_now()

    def latest_video_frame_for_thread(
        self,
        thread_id: str,
        *,
        max_age_seconds: float = 5.0,
    ) -> tuple[bytes, str | None] | None:
        """Return the latest live camera frame for a thread.

        Only returns a frame when the camera is *currently* active: the
        session must be open and the frame must be fresher than
        ``max_age_seconds``. Frames arrive at a few Hz while the camera is on,
        so a stale frame means the camera has since been turned off.
        """
        cutoff = datetime.now(UTC).timestamp() - max_age_seconds
        with self._lock:
            for stats in self._sessions.values():
                if stats.thread_id != thread_id:
                    continue
                if stats.status != "active":
                    continue
                if stats.last_video_frame_jpeg is None or stats.last_video_frame_at is None:
                    continue
                try:
                    captured_ts = datetime.fromisoformat(stats.last_video_frame_at).timestamp()
                except ValueError:
                    continue
                if captured_ts < cutoff:
                    continue
                return stats.last_video_frame_jpeg, stats.last_video_frame_at
            return None

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
            return _public_snapshot(stats) if stats is not None else None

    def snapshots(self) -> list[dict[str, Any]]:
        with self._lock:
            return [_public_snapshot(stats) for stats in self._sessions.values()]

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


speech_pipelines = SpeechPipelineManager(media_sessions)


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
            self._video_queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=1)
            self._last_log_at = 0.0
            self._last_jpeg_encode_at = 0.0

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
            webrtc_id = self._webrtc_id()
            media_sessions.record_video(
                self.session_id,
                webrtc_id=webrtc_id,
                width=int(width),
                height=int(height),
            )
            if self._video_queue.full():
                self._video_queue.get_nowait()
            self._video_queue.put_nowait(frame)
            self._maybe_capture_frame_for_vision(frame, webrtc_id)
            self._log_progress()

        def _maybe_capture_frame_for_vision(self, frame, webrtc_id: str | None) -> None:
            now = time.monotonic()
            if now - self._last_jpeg_encode_at < 0.33:
                return
            self._last_jpeg_encode_at = now
            jpeg_bytes = encode_frame_to_jpeg(frame)
            if jpeg_bytes is None:
                return
            media_sessions.store_video_frame_jpeg(
                self.session_id,
                webrtc_id=webrtc_id,
                jpeg_bytes=jpeg_bytes,
            )

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
