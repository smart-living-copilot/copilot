"""Capture LiveKit camera frames into the in-process media registry.

The voice worker subscribes to a participant's camera track and stores the
latest JPEG frame so the ``look_at_camera`` tool can describe what the user is
showing. LiveKit imports stay local to the functions so non-worker roles do not
need the ``livekit`` packages installed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress
from typing import Any

from copilot.media.ingress import encode_frame_to_jpeg, media_sessions

logger = logging.getLogger(__name__)

# Throttle JPEG encoding to ~3 fps; look_at_camera only needs a recent frame.
_MIN_ENCODE_INTERVAL_SECONDS = 0.33


def _media_session_id(ctx: Any, thread_id: str) -> str:
    room_name = getattr(getattr(ctx, "room", None), "name", "")
    if isinstance(room_name, str) and room_name:
        return f"livekit-{room_name}"
    return f"livekit-{thread_id}"


def _frame_to_bgr_array(frame: Any):
    import numpy as np
    from livekit.rtc.video_frame import proto_video

    rgb_frame = (
        frame
        if frame.type == proto_video.VideoBufferType.RGB24
        else frame.convert(proto_video.VideoBufferType.RGB24)
    )
    rgb_array = np.frombuffer(rgb_frame.data, dtype=np.uint8).reshape(
        (rgb_frame.height, rgb_frame.width, 3)
    )
    return rgb_array[:, :, ::-1].copy()


async def _capture_video_track(
    *,
    track: Any,
    session_id: str,
    thread_id: str,
) -> None:
    from livekit import rtc
    from livekit.rtc.video_frame import proto_video

    media_sessions.set_metadata(session_id, thread_id=thread_id)
    try:
        stream = rtc.VideoStream.from_track(
            track=track,
            format=proto_video.VideoBufferType.RGB24,
            capacity=1,
        )
    except Exception:
        logger.exception("Failed to open LiveKit VideoStream for thread_id=%s", thread_id)
        return

    last_jpeg_encode_at = 0.0
    logged_first_snapshot = False
    try:
        async for event in stream:
            frame = event.frame
            media_sessions.record_video(
                session_id,
                width=int(frame.width),
                height=int(frame.height),
            )

            now = time.monotonic()
            if now - last_jpeg_encode_at < _MIN_ENCODE_INTERVAL_SECONDS:
                continue
            last_jpeg_encode_at = now

            try:
                jpeg_bytes = encode_frame_to_jpeg(_frame_to_bgr_array(frame))
            except Exception:
                logger.debug("Failed to capture LiveKit video frame for vision", exc_info=True)
                continue
            if jpeg_bytes is None:
                continue

            media_sessions.store_video_frame_jpeg(session_id, jpeg_bytes=jpeg_bytes)
            if not logged_first_snapshot:
                logger.info("LiveKit camera snapshot available for thread_id=%s", thread_id)
                logged_first_snapshot = True
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("LiveKit camera capture failed for thread_id=%s", thread_id)
    finally:
        await stream.aclose()


class _LiveKitCameraCapture:
    def __init__(
        self,
        *,
        room: Any,
        video_kind: Any,
        session_id: str,
        thread_id: str,
    ) -> None:
        self._room = room
        self._video_kind = video_kind
        self._session_id = session_id
        self._thread_id = thread_id
        self._capture_tasks_by_track_sid: dict[str, asyncio.Task[None]] = {}
        self._stop_tasks: set[asyncio.Task[None]] = set()
        self._handlers = {
            "track_published": self._on_track_published,
            "track_subscribed": self._on_track_subscribed,
            "track_unsubscribed": self._on_track_unsubscribed,
        }

    @staticmethod
    def _track_sid(track: Any) -> str:
        sid = getattr(track, "sid", "")
        return sid if isinstance(sid, str) and sid else str(id(track))

    def _is_video_track(self, track: Any) -> bool:
        return getattr(track, "kind", None) == self._video_kind

    def _is_video_publication(self, publication: Any) -> bool:
        return getattr(publication, "kind", None) == self._video_kind

    def start(self) -> None:
        media_sessions.set_metadata(self._session_id, thread_id=self._thread_id)
        for name, handler in self._handlers.items():
            self._room.on(name, handler)
        self._start_existing_tracks()

    def _start_existing_tracks(self) -> None:
        for participant in getattr(self._room, "remote_participants", {}).values():
            for publication in getattr(participant, "track_publications", {}).values():
                self._ensure_subscribed(publication)
                track = getattr(publication, "track", None)
                if track is not None and getattr(publication, "subscribed", False):
                    self._start_capture(track)

    def _ensure_subscribed(self, publication: Any) -> None:
        """Explicitly subscribe to a remote video publication."""
        if not self._is_video_publication(publication):
            return
        set_subscribed = getattr(publication, "set_subscribed", None)
        if set_subscribed is None or getattr(publication, "subscribed", False):
            return
        try:
            set_subscribed(True)
            logger.debug(
                "Requested LiveKit video subscription for thread_id=%s sid=%s",
                self._thread_id,
                getattr(publication, "sid", "?"),
            )
        except Exception:
            logger.exception("Failed to subscribe to LiveKit video publication")

    def _start_capture(self, track: Any) -> None:
        if not self._is_video_track(track):
            return
        sid = self._track_sid(track)
        if sid in self._capture_tasks_by_track_sid:
            return
        task = asyncio.create_task(
            _capture_video_track(
                track=track,
                session_id=self._session_id,
                thread_id=self._thread_id,
            ),
            name=f"livekit-video-capture-{sid}",
        )
        self._capture_tasks_by_track_sid[sid] = task
        logger.info(
            "Started LiveKit camera capture for thread_id=%s track_sid=%s",
            self._thread_id,
            sid,
        )

    async def _stop_capture(self, track: Any) -> None:
        sid = self._track_sid(track)
        task = self._capture_tasks_by_track_sid.pop(sid, None)
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    def _on_track_published(self, publication: Any, _participant: Any) -> None:
        self._ensure_subscribed(publication)

    def _on_track_subscribed(self, track: Any, _publication: Any, _participant: Any) -> None:
        self._start_capture(track)

    def _on_track_unsubscribed(
        self,
        track: Any,
        _publication: Any,
        _participant: Any,
    ) -> None:
        task = asyncio.create_task(
            self._stop_capture(track),
            name=f"livekit-video-stop-{self._track_sid(track)}",
        )
        self._stop_tasks.add(task)
        task.add_done_callback(self._stop_tasks.discard)

    async def close(self) -> None:
        for name, handler in self._handlers.items():
            self._room.off(name, handler)
        if self._stop_tasks:
            await asyncio.gather(*self._stop_tasks, return_exceptions=True)
        for task in self._capture_tasks_by_track_sid.values():
            task.cancel()
        if self._capture_tasks_by_track_sid:
            await asyncio.gather(
                *self._capture_tasks_by_track_sid.values(),
                return_exceptions=True,
            )
        media_sessions.close(self._session_id)


@asynccontextmanager
async def livekit_camera_capture(ctx: Any, thread_id: str):
    """Subscribe to remote camera tracks and capture frames while active."""
    from livekit import rtc

    room = getattr(ctx, "room", None)
    if room is None:
        yield
        return

    session_id = _media_session_id(ctx, thread_id)
    capture = _LiveKitCameraCapture(
        room=room,
        video_kind=rtc.TrackKind.KIND_VIDEO,
        session_id=session_id,
        thread_id=thread_id,
    )
    capture.start()

    try:
        yield
    finally:
        await capture.close()
