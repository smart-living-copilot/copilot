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
from contextlib import asynccontextmanager
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
    from livekit.rtc.video_frame import proto_video
    import numpy as np

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


@asynccontextmanager
async def livekit_camera_capture(ctx: Any, thread_id: str):
    """Subscribe to remote camera tracks and capture frames while active."""
    from livekit import rtc

    room = getattr(ctx, "room", None)
    if room is None:
        yield
        return

    session_id = _media_session_id(ctx, thread_id)
    media_sessions.set_metadata(session_id, thread_id=thread_id)
    tasks_by_track_sid: dict[str, asyncio.Task[None]] = {}

    def track_sid(track: Any) -> str:
        sid = getattr(track, "sid", "")
        return sid if isinstance(sid, str) and sid else str(id(track))

    def is_video_track(track: Any) -> bool:
        return getattr(track, "kind", None) == rtc.TrackKind.KIND_VIDEO

    def is_video_publication(publication: Any) -> bool:
        return getattr(publication, "kind", None) == rtc.TrackKind.KIND_VIDEO

    def ensure_subscribed(publication: Any) -> None:
        """Explicitly subscribe to a remote video publication.

        RoomIO only subscribes to the audio it needs, so the camera track is
        never subscribed unless we ask for it. Requesting the subscription here
        is what drives the ``track_subscribed`` event that starts capture.
        """
        if not is_video_publication(publication):
            return
        set_subscribed = getattr(publication, "set_subscribed", None)
        if set_subscribed is None or getattr(publication, "subscribed", False):
            return
        try:
            set_subscribed(True)
            logger.debug(
                "Requested LiveKit video subscription for thread_id=%s sid=%s",
                thread_id,
                getattr(publication, "sid", "?"),
            )
        except Exception:
            logger.exception("Failed to subscribe to LiveKit video publication")

    def start_capture(track: Any) -> None:
        if not is_video_track(track):
            return
        sid = track_sid(track)
        if sid in tasks_by_track_sid:
            return
        task = asyncio.create_task(
            _capture_video_track(track=track, session_id=session_id, thread_id=thread_id),
            name=f"livekit-video-capture-{sid}",
        )
        tasks_by_track_sid[sid] = task
        logger.info(
            "Started LiveKit camera capture for thread_id=%s track_sid=%s", thread_id, sid
        )

    async def stop_capture(track: Any) -> None:
        sid = track_sid(track)
        task = tasks_by_track_sid.pop(sid, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def on_track_published(publication: Any, _participant: Any) -> None:
        ensure_subscribed(publication)

    def on_track_subscribed(track: Any, _publication: Any, _participant: Any) -> None:
        start_capture(track)

    def on_track_unsubscribed(track: Any, _publication: Any, _participant: Any) -> None:
        asyncio.create_task(stop_capture(track))

    room.on("track_published", on_track_published)
    room.on("track_subscribed", on_track_subscribed)
    room.on("track_unsubscribed", on_track_unsubscribed)

    for participant in getattr(room, "remote_participants", {}).values():
        for publication in getattr(participant, "track_publications", {}).values():
            ensure_subscribed(publication)
            track = getattr(publication, "track", None)
            if track is not None and getattr(publication, "subscribed", False):
                start_capture(track)

    try:
        yield
    finally:
        room.off("track_published", on_track_published)
        room.off("track_subscribed", on_track_subscribed)
        room.off("track_unsubscribed", on_track_unsubscribed)
        for task in tasks_by_track_sid.values():
            task.cancel()
        if tasks_by_track_sid:
            await asyncio.gather(*tasks_by_track_sid.values(), return_exceptions=True)
        media_sessions.close(session_id)
