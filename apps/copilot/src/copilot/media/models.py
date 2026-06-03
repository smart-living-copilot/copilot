"""Live media data structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MediaSessionStats:
    id: str
    created_at: str
    updated_at: str
    status: str = "active"
    thread_id: str | None = None
    video_frames: int = 0
    video_width: int | None = None
    video_height: int | None = None
    last_video_frame_jpeg: bytes | None = field(default=None, repr=False)
    last_video_frame_at: str | None = None
