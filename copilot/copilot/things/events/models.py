from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ThingEventOutboxRow:
    id: int
    event_type: str
    thing_id: str
    event_hash: str
    payload_json: dict[str, Any]
    created_at: datetime | None = None
    published_at: datetime | None = None
    attempt_count: int = 0
    last_error: str = ""
