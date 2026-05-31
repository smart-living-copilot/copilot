from __future__ import annotations

import asyncio
from dataclasses import dataclass

import redis.asyncio as redis
from redis.exceptions import ResponseError


@dataclass
class StreamConsumerState:
    task: asyncio.Task[None] | None = None
    loop_running: bool = False
    last_error: str = ""
    last_entry_id: str = ""


async def ensure_stream_group(
    redis_client: redis.Redis,
    *,
    stream: str,
    group: str,
) -> None:
    try:
        await redis_client.xgroup_create(
            name=stream,
            groupname=group,
            id="0",
            mkstream=True,
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
