from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

import redis.asyncio as redis

from copilot.core.settings import Settings
from copilot.jobs.resources import EventSubscriptionReconciler
from copilot.jobs.stores import JobStore
from copilot.jobs.stream import StreamConfig, ensure_stream_group, parse_runtime_stream_fields
from copilot.jobs.taskiq_app import run_job_task
from copilot.clients.wot_runtime import WotRuntimeClient

logger = logging.getLogger(__name__)

EVENT_SUBSCRIPTION_SYNC_LOCK_KEY = "copilot:jobs:event-subscriptions:sync"
EVENT_SUBSCRIPTION_SYNC_LOCK_TTL_SECONDS = 300

_RELEASE_SYNC_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


class JobEventConsumer:
    """Consumes WoT runtime event streams and enqueues matching event jobs."""

    def __init__(
        self,
        settings: Settings,
        *,
        repo: JobStore | None = None,
        runtime_client: WotRuntimeClient | None = None,
    ) -> None:
        self._settings = settings
        self._repo = repo or JobStore()
        self._runtime_client = runtime_client or WotRuntimeClient(settings)
        self._event_subscriptions = EventSubscriptionReconciler(
            repo=self._repo,
            runtime_client=self._runtime_client,
        )
        self._redis: redis.Redis | None = None
        self._stream = StreamConfig(
            stream=settings.wot_runtime_stream,
            group=settings.jobs_events_group,
            consumer=settings.jobs_events_consumer,
            batch_size=settings.jobs_stream_batch_size,
            poll_block_ms=settings.jobs_stream_poll_block_ms,
            claim_idle_ms=settings.jobs_stream_claim_idle_ms,
        )

    async def start(self) -> None:
        await self._sync_event_subscriptions_with_lock()

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await self._connect_redis()
                await self._run_connected_loop(stop_event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Job event consumer failed: %s", exc, exc_info=exc)
                await asyncio.sleep(2)
            finally:
                if self._redis is not None:
                    await self._redis.aclose()
                    self._redis = None

    async def _sync_event_subscriptions(self) -> None:
        await self._event_subscriptions.sync()

    async def _sync_event_subscriptions_with_lock(self) -> None:
        token = str(uuid4())
        client = redis.from_url(self._settings.redis_url, decode_responses=True)
        try:
            acquired = await client.set(
                EVENT_SUBSCRIPTION_SYNC_LOCK_KEY,
                token,
                ex=EVENT_SUBSCRIPTION_SYNC_LOCK_TTL_SECONDS,
                nx=True,
            )
            if not acquired:
                logger.info("Skipping event subscription sync; another worker owns the lock.")
                return

            try:
                await self._sync_event_subscriptions()
            finally:
                await client.eval(
                    _RELEASE_SYNC_LOCK_SCRIPT,
                    1,
                    EVENT_SUBSCRIPTION_SYNC_LOCK_KEY,
                    token,
                )
        finally:
            await client.aclose()

    async def _connect_redis(self) -> None:
        self._redis = redis.from_url(
            self._settings.redis_url,
            decode_responses=True,
            socket_timeout=self._stream.poll_block_ms / 1000 + 5,
            socket_keepalive=True,
        )
        await ensure_stream_group(
            self._redis,
            stream=self._stream.stream,
            group=self._stream.group,
        )
        logger.info(
            "Job event consumer reading stream '%s' with group '%s' as consumer '%s'.",
            self._stream.stream,
            self._stream.group,
            self._stream.consumer,
        )

    async def _run_connected_loop(self, stop_event: asyncio.Event) -> None:
        redis_client = self._redis
        if redis_client is None:
            raise RuntimeError("Redis client is not connected")

        while not stop_event.is_set():
            stale_entries = await self._claim_stale_entries(redis_client)
            if stale_entries:
                await self._process_entries(redis_client, stale_entries)
                continue

            records = await redis_client.xreadgroup(
                groupname=self._stream.group,
                consumername=self._stream.consumer,
                streams={self._stream.stream: ">"},
                count=self._stream.batch_size,
                block=self._stream.poll_block_ms,
            )
            if not records:
                continue

            for _stream_name, entries in records:
                await self._process_entries(redis_client, entries)

    async def _claim_stale_entries(
        self,
        redis_client: redis.Redis,
    ) -> list[tuple[str, dict[str, str]]]:
        next_start = "0-0"
        claimed: list[tuple[str, dict[str, str]]] = []

        while True:
            next_start, entries, _deleted = await redis_client.xautoclaim(
                self._stream.stream,
                self._stream.group,
                self._stream.consumer,
                self._stream.claim_idle_ms,
                start_id=next_start,
                count=self._stream.batch_size,
            )
            if entries:
                claimed.extend(entries)
            if next_start == "0-0" or not entries:
                break

        return claimed

    async def _process_entries(
        self,
        redis_client: redis.Redis,
        entries: list[tuple[str, dict[str, str]]],
    ) -> None:
        for entry_id, fields in entries:
            await self._handle_stream_entry(fields)
            await redis_client.xack(self._stream.stream, self._stream.group, entry_id)

    async def _handle_stream_entry(self, fields: dict[str, str]) -> None:
        event = parse_runtime_stream_fields(fields)
        if event["event_type"] != "event_received":
            return

        subscription_id = event.get("subscription_id")
        if not subscription_id:
            return

        jobs = await self._repo.list_event_jobs_for_subscription(subscription_id)
        for job in jobs:
            await run_job_task.kiq(
                job_id=job.id,
                trigger={
                    "source": "event",
                    "thing_id": event.get("thing_id"),
                    "event_name": event.get("name"),
                    "payload_base64": event.get("payload_base64"),
                    "content_type": event.get("content_type"),
                    "timestamp": event.get("timestamp"),
                },
            )
