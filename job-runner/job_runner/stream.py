from __future__ import annotations

from dataclasses import dataclass

import redis.asyncio as redis


@dataclass
class StreamConfig:
    stream: str
    group: str
    consumer: str
    batch_size: int
    poll_block_ms: int
    claim_idle_ms: int


async def ensure_stream_group(
    redis_client: redis.Redis,
    *,
    stream: str,
    group: str,
) -> None:
    try:
        await redis_client.xgroup_create(name=stream, groupname=group, id="$", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def parse_runtime_stream_fields(fields: dict[str, str]) -> dict[str, str]:
    return {
        "event_type": fields.get("event_type", ""),
        "thing_id": fields.get("thing_id", ""),
        "name": fields.get("name", ""),
        "subscription_id": fields.get("subscription_id", ""),
        "payload_base64": fields.get("payload_base64", ""),
        "content_type": fields.get("content_type", ""),
        "timestamp": fields.get("timestamp", ""),
    }
