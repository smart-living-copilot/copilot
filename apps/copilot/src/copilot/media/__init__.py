"""LiveKit media support for agent vision features.

The media package provides a session registry for camera streams and helpers to
encode raw frames into JPEG payloads. It is used by vision-facing tools to
capture and serve recent frame context.
"""

from copilot.media.ingress import MediaSessionRegistry, encode_frame_to_jpeg, media_sessions
from copilot.media.models import MediaSessionStats
from copilot.media.snapshot_notifications import (
    SNAPSHOT_EVENT_TYPE,
    SNAPSHOT_TOPIC,
    SnapshotNotifierRegistry,
    snapshot_notifiers,
)

__all__ = [
    "MediaSessionRegistry",
    "MediaSessionStats",
    "SNAPSHOT_EVENT_TYPE",
    "SNAPSHOT_TOPIC",
    "SnapshotNotifierRegistry",
    "encode_frame_to_jpeg",
    "media_sessions",
    "snapshot_notifiers",
]
