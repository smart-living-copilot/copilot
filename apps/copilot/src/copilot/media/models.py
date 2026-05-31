"""Shared browser media data structures."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    last_video_frame_jpeg: bytes | None = field(default=None, repr=False)
    last_video_frame_at: str | None = None
    transcript_count: int = 0
    latest_transcript_text: str | None = None
    latest_assistant_text: str | None = None
    assistant_response_pending: bool = False
    transcripts: list[MediaTranscript] = field(default_factory=list)
    tts_requests: int = 0
    tts_audio_frames: int = 0
    latest_tts_text: str | None = None
    latest_tts_error: str | None = None
