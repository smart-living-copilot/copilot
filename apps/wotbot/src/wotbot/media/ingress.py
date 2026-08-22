"""LiveKit media session helpers for camera-backed tools."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from threading import Lock
from typing import Any

from wotbot.core.settings import Settings
from wotbot.core.time import utc_now
from wotbot.media.models import MediaSessionStats

logger = logging.getLogger(__name__)
_settings = Settings()


def _utc_now() -> str:
    return utc_now().isoformat()


def encode_frame_to_jpeg(frame: Any) -> bytes | None:
    """Encode an HxWx{3,4} uint8 video frame to JPEG bytes.

    LiveKit camera frames are normalized to OpenCV-style BGR before they reach
    this helper. Pillow expects RGB, so 3-channel frames are swapped before
    encoding.
    """
    try:
        from io import BytesIO

        import numpy as np
        from PIL import Image
    except Exception:  # pragma: no cover - PIL/numpy missing at import time.
        logger.warning("Pillow/numpy unavailable; camera frame capture disabled")
        return None

    try:
        if not hasattr(frame, "shape") or frame.ndim < 2:
            return None
        array = np.asarray(frame)
        if array.dtype != np.uint8:
            array = array.astype(np.uint8, copy=False)
        if array.ndim == 3 and array.shape[2] >= 3:
            array = array[:, :, :3][:, :, ::-1]
        image = Image.fromarray(array)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        max_dimension = _settings.camera_frame_max_dimension
        image.thumbnail((max_dimension, max_dimension))
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=_settings.camera_frame_jpeg_quality)
        return buffer.getvalue()
    except Exception:
        logger.debug("Failed to encode video frame to JPEG", exc_info=True)
        return None


def _public_snapshot(stats: MediaSessionStats) -> dict[str, Any]:
    data = asdict(stats)
    data.pop("last_video_frame_jpeg", None)
    return data


class MediaSessionRegistry:
    """In-process LiveKit camera frame registry keyed by room/session id."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[str, MediaSessionStats] = {}

    def ensure(self, session_id: str) -> MediaSessionStats:
        now = _utc_now()
        with self._lock:
            stats = self._sessions.get(session_id)
            if stats is None:
                stats = MediaSessionStats(
                    id=session_id,
                    created_at=now,
                    updated_at=now,
                )
                self._sessions[session_id] = stats
            stats.updated_at = now
            stats.status = "active"
            return stats

    def set_metadata(self, session_id: str, *, thread_id: str | None) -> MediaSessionStats:
        stats = self.ensure(session_id)
        with self._lock:
            stats.thread_id = thread_id
            stats.updated_at = _utc_now()
            return stats

    def record_video(
        self,
        session_id: str,
        *,
        width: int,
        height: int,
    ) -> None:
        stats = self.ensure(session_id)
        with self._lock:
            stats.video_frames += 1
            stats.video_width = width
            stats.video_height = height
            stats.updated_at = _utc_now()

    def store_video_frame_jpeg(
        self,
        session_id: str,
        *,
        jpeg_bytes: bytes,
    ) -> None:
        stats = self.ensure(session_id)
        with self._lock:
            stats.last_video_frame_jpeg = jpeg_bytes
            stats.last_video_frame_at = _utc_now()

    def latest_video_frame_for_thread(
        self,
        thread_id: str,
        *,
        max_age_seconds: float = 5.0,
    ) -> tuple[bytes, str | None] | None:
        """Return the latest active LiveKit camera frame for a thread."""
        cutoff = utc_now().timestamp() - max_age_seconds
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

    def clear_video_frame(self, session_id: str) -> None:
        """Discard the last encoded frame when a camera track stops."""
        with self._lock:
            stats = self._sessions.get(session_id)
            if stats is None:
                return
            stats.last_video_frame_jpeg = None
            stats.last_video_frame_at = None
            stats.updated_at = _utc_now()

    def close(self, session_id: str) -> None:
        with self._lock:
            stats = self._sessions.get(session_id)
            if stats is None:
                return
            stats.status = "closed"
            stats.last_video_frame_jpeg = None
            stats.last_video_frame_at = None
            stats.updated_at = _utc_now()

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            stats = self._sessions.get(session_id)
            return _public_snapshot(stats) if stats is not None else None

    def snapshots(self) -> list[dict[str, Any]]:
        with self._lock:
            return [_public_snapshot(stats) for stats in self._sessions.values()]


media_sessions = MediaSessionRegistry()
