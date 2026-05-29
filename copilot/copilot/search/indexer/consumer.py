from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import redis.asyncio as redis

from copilot.config import Settings
from copilot.search.indexer.runtime import SearchIndexerStreamConfig
from copilot.search.indexer.service import SearchIndexerService
from copilot.search.indexer.store import SearchVectorStore
from copilot.search.indexer.stream_utils import parse_stream_event
from copilot.stream_runtime import StreamConsumerState, ensure_stream_group


logger = logging.getLogger(__name__)


@dataclass
class SearchIndexerConsumerState(StreamConsumerState):
    pass


class SearchIndexerStreamConsumer:
    def __init__(
        self,
        *,
        settings: Settings,
        state: SearchIndexerConsumerState,
        vector_store: SearchVectorStore | None = None,
    ) -> None:
        self._settings = settings
        self._stream = SearchIndexerStreamConfig.from_settings(settings)
        self._state = state
        self._redis: redis.Redis | None = None
        self._service = SearchIndexerService(settings, vector_store=vector_store)

    async def start(self) -> None:
        await self._service.start()

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        await self._service.close()

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        self._state.loop_running = True
        self._state.last_error = ""
        try:
            while not stop_event.is_set():
                try:
                    await self._connect_redis()
                    await self._run_connected_loop(stop_event)

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._state.last_error = str(exc)
                    logger.error("Search indexer listener error: %s", exc)
                    logger.info("Retrying in %ss", self._stream.retry_seconds)
                    await asyncio.sleep(self._stream.retry_seconds)
                finally:
                    if self._redis is not None:
                        await self._redis.aclose()
                        self._redis = None
        finally:
            self._state.loop_running = False

    async def _connect_redis(self) -> None:
        logger.info(
            "Search indexer connecting to Redis at %s...",
            self._settings.REDIS_URL,
        )
        self._redis = redis.from_url(
            self._settings.REDIS_URL,
            decode_responses=True,
        )
        await ensure_stream_group(
            self._redis,
            stream=self._stream.stream,
            group=self._stream.group,
        )
        logger.info(
            "Search indexer reading from stream '%s' with group '%s' as consumer '%s'.",
            self._stream.stream,
            self._stream.group,
            self._stream.consumer,
        )

    async def _run_connected_loop(self, stop_event: asyncio.Event) -> None:
        redis_client = self._redis
        if redis_client is None:
            raise RuntimeError("Search indexer Redis client is not connected")

        while not stop_event.is_set():
            try:
                stale_entries = await self._claim_stale_entries(redis_client)
                if stale_entries:
                    await self._process_entries(
                        redis_client,
                        stale_entries,
                        source="reclaimed entry",
                    )
                    continue

                records = await self._read_stream_records(redis_client)
                if not records:
                    continue

                for _stream_name, entries in records:
                    await self._process_entries(
                        redis_client,
                        entries,
                        source="stream entry",
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._state.last_error = str(exc)
                logger.error("Search indexer inner loop error: %s", exc)
                await asyncio.sleep(2)

    async def _read_stream_records(
        self,
        redis_client: redis.Redis,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        return await redis_client.xreadgroup(
            groupname=self._stream.group,
            consumername=self._stream.consumer,
            streams={self._stream.stream: ">"},
            count=self._stream.batch_size,
            block=self._stream.poll_block_ms,
        )

    async def _process_entries(
        self,
        redis_client: redis.Redis,
        entries: list[tuple[str, dict[str, str]]],
        *,
        source: str,
    ) -> None:
        for entry_id, fields in entries:
            try:
                await self._process_entry(redis_client, entry_id, fields)
            except Exception as exc:
                self._state.last_error = str(exc)
                logger.error("Error processing %s %s: %s", source, entry_id, exc)

    async def _claim_stale_entries(
        self, redis_client: redis.Redis
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

    async def _process_entry(
        self,
        redis_client: redis.Redis,
        entry_id: str,
        fields: dict[str, str],
    ) -> None:
        event = parse_stream_event(fields)
        logger.info(
            "Search indexer received event: %s for thing %s",
            event.get("eventType"),
            event.get("id"),
        )
        await self._service.process_event(event)
        await redis_client.xack(
            self._stream.stream,
            self._stream.group,
            entry_id,
        )
        self._state.last_entry_id = entry_id
        self._state.last_error = ""
