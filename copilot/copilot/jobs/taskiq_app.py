from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from taskiq import TaskiqEvents, TaskiqScheduler
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from copilot.core.settings import Settings
from copilot.jobs.constants import JOB_TASK_QUEUE_NAME, RUN_JOB_TASK_NAME
from copilot.jobs.executor import close_job_executor, get_job_executor
from copilot.jobs.schedule import build_schedule_source

if TYPE_CHECKING:
    from copilot.jobs.events import JobEventConsumer

logger = logging.getLogger(__name__)

settings = Settings()

result_backend = RedisAsyncResultBackend(
    settings.redis_url,
    result_ex_time=max(settings.job_task_timeout_seconds * 2, 600),
)
broker = RedisStreamBroker(
    url=settings.redis_url,
    queue_name=JOB_TASK_QUEUE_NAME,
    consumer_group_name="job_workers",
).with_result_backend(result_backend)
schedule_source = build_schedule_source(settings)
scheduler = TaskiqScheduler(
    broker=broker,
    sources=[schedule_source],
)


# The worker also hosts the WoT event consumer: it joins the Redis consumer group,
# so running it inside every worker load-balances events and removes the need for a
# separate ``job-events`` container.
_event_consumer: JobEventConsumer | None = None
_event_stop: asyncio.Event | None = None
_event_task: asyncio.Task[None] | None = None


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _worker_startup(_state: object) -> None:
    get_job_executor()

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


@broker.task(task_name=RUN_JOB_TASK_NAME)
async def run_job_task(job_id: str, trigger: dict[str, Any]) -> dict[str, Any]:
    return await get_job_executor().run_job(job_id, trigger)
