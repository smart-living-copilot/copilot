import json
import logging
from typing import Any, Protocol

import redis

from copilot.core.time import utc_now

logger = logging.getLogger(__name__)


class ThingEventPublisher(Protocol):
    def publish(self, event: dict[str, Any]) -> None: ...

    def close(self) -> None: ...


class ValkeyThingEventStreamPublisher:
    def __init__(self, url: str, stream: str):
        self._stream = stream
        self._client = redis.Redis.from_url(url, decode_responses=True)

    def publish(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        self._client.xadd(
            self._stream,
            {
                "event_json": payload,
                "event_type": str(event.get("eventType", "")),
                "thing_id": str(event.get("id", "")),
                "event_hash": str(event.get("hash", "")),
                "timestamp": utc_now().isoformat(),
            },
        )

    def close(self) -> None:
        self._client.close()


class NoopThingEventPublisher:
    def publish(self, event: dict[str, Any]) -> None:
        logger.debug("Skipping event publish: %s", event.get("eventType"))

    def close(self) -> None:
        return None
