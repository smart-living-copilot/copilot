from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from taskiq import TaskiqEvents

from copilot.jobs.executor import close_job_executor, get_job_executor
from copilot.jobs.taskiq_app import broker, run_job_task, settings

if TYPE_CHECKING:
    from copilot.jobs.events import JobEventConsumer

logger = logging.getLogger(__name__)


# The worker also hosts the WoT event consumer: it joins the Redis consumer group,
# so running it inside every worker load-balances events and removes the need for a
# separate ``job-events`` container.
_event_consumer: JobEventConsumer | None = None
_event_stop: asyncio.Event | None = None
_event_task: asyncio.Task[None] | None = None


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _worker_startup(_state: object) -> None:
    executor = get_job_executor()
    await executor.reconcile_stale_running_runs()

    from copilot.jobs.events import JobEventConsumer  # lazy: avoids import cycle

    global _event_consumer, _event_stop, _event_task
    _event_consumer = JobEventConsumer(settings)
    _event_stop = asyncio.Event()
    await _event_consumer.start()
    _event_task = asyncio.create_task(_event_consumer.run_forever(_event_stop))
    logger.info("Worker started WoT event consumer.")


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _worker_shutdown(_state: object) -> None:
    global _event_consumer, _event_stop, _event_task
    if _event_stop is not None:
        _event_stop.set()
    if _event_task is not None:
        try:
            await _event_task
        except asyncio.CancelledError:
            pass
        _event_task = None
    if _event_consumer is not None:
        await _event_consumer.close()
        _event_consumer = None
    _event_stop = None
    await close_job_executor()


__all__ = ["broker", "run_job_task"]
