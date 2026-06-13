from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as redis

from copilot.core.settings import Settings
from copilot.jobs.stores import JobStore

logger = logging.getLogger(__name__)


class JobRunEventPublisher:
    """Publishes compact job/run updates for clients subscribed to job activity."""

    def __init__(
        self,
        settings: Settings,
        *,
        repo: JobStore | None = None,
    ) -> None:
        self._settings = settings
        self._repo = repo or JobStore()

    async def publish_job_run(self, job_id: str, *, run_id: str | None = None) -> str | None:
        try:
            job = await self._repo.get_job(job_id)
        except Exception as exc:
            logger.warning("Failed to load job %s for run event: %s", job_id, exc)
            return None

        payload = {
            "type": "job_run",
            "job": job.model_dump(mode="json", by_alias=True),
        }
        if run_id is not None:
            try:
                run = await self._repo.get_job_run(run_id)
                payload["run"] = run.model_dump(mode="json")
            except Exception as exc:
                logger.warning("Failed to load job run %s for run event: %s", run_id, exc)
        client = redis.from_url(self._settings.redis_url, decode_responses=True)
        try:
            return await client.xadd(
                self._settings.jobs_run_events_stream,
                {"payload": json.dumps(payload, ensure_ascii=True)},
            )
        finally:
            await client.aclose()


class JobRunEventStream:
    """Reads job run update events from Redis for server-sent event clients."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def subscribe(
        self,
        *,
        last_event_id: str | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        start_id = last_event_id or "$"
        while True:
            client = self._stream_client()
            try:
                async for event_id, event in self._read_events(client, start_id):
                    start_id = event_id
                    yield event_id, event
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Job run event stream failed: %s", exc)
                await asyncio.sleep(2)
            finally:
                await client.aclose()

    def _stream_client(self):
        return redis.from_url(
            self._settings.redis_url,
            decode_responses=True,
            socket_timeout=35,
            socket_keepalive=True,
        )

    async def _read_events(
        self,
        client: Any,
        start_id: str,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        while True:
            records = await client.xread(
                streams={self._settings.jobs_run_events_stream: start_id},
                count=20,
                block=30000,
            )
            for event_id, event in _decode_stream_records(records):
                start_id = event_id
                yield event_id, event


def _decode_stream_records(records: Any) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for _stream_name, entries in records or []:
        for event_id, fields in entries:
            event = _decode_stream_event(event_id, fields)
            if event is not None:
                events.append((event_id, event))
    return events


def _decode_stream_event(event_id: str, fields: Any) -> dict[str, Any] | None:
    payload = fields.get("payload") if isinstance(fields, dict) else None
    if not payload:
        return None
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Ignoring invalid job run event %s", event_id)
        return None
    return event if isinstance(event, dict) else None
