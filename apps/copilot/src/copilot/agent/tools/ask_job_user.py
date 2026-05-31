"""Worker-only tool for pausing a background job for human input."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


@tool
async def ask_job_user(
    question: str,
    config: RunnableConfig,
    context: str | None = None,
) -> dict[str, str | None]:
    """Ask the job owner for input and pause the background job.

    Use this only from a background job when the job cannot safely continue
    without user input. After calling this tool, stop and wait for a reply.
    """
    configurable = config.get("configurable", {})
    return {
        "status": "waiting_for_input",
        "question": question.strip(),
        "context": context,
        "job_id": configurable.get("job_id"),
        "run_id": configurable.get("run_id"),
        "thread_id": configurable.get("thread_id"),
    }
