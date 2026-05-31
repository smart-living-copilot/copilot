from __future__ import annotations

from typing import Any

from taskiq import TaskiqScheduler
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from copilot.core.settings import Settings
from copilot.jobs.constants import JOB_TASK_QUEUE_NAME, RUN_JOB_TASK_NAME
from copilot.jobs.executor import get_job_executor
from copilot.jobs.schedule import build_schedule_source

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


@broker.task(task_name=RUN_JOB_TASK_NAME)
async def run_job_task(job_id: str, trigger: dict[str, Any]) -> dict[str, Any]:
    return await get_job_executor().run_job(job_id, trigger)
