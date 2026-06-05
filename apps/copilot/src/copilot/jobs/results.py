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
            "job": job.model_dump(mode="json"),
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
            client = redis.from_url(
                self._settings.redis_url,
                decode_responses=True,
                socket_timeout=35,
                socket_keepalive=True,
            )
            try:
                while True:
                    records = await client.xread(
                        streams={self._settings.jobs_run_events_stream: start_id},
                        count=20,
                        block=30000,
                    )
                    if not records:
                        continue

                    for _stream_name, entries in records:
                        for event_id, fields in entries:
                            start_id = event_id
                            payload = fields.get("payload")
                            if not payload:
                                continue
                            try:
                                event = json.loads(payload)
                            except json.JSONDecodeError:
                                logger.warning("Ignoring invalid job run event %s", event_id)
                                continue
                            if isinstance(event, dict):
                                yield event_id, event
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Job run event stream failed: %s", exc)
                await asyncio.sleep(2)
            finally:
                await client.aclose()
